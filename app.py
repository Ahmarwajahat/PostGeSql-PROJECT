from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import psycopg2
from psycopg2 import sql, OperationalError
from datetime import datetime
import os
from dotenv import load_dotenv
import math

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-here')

# Database configuration
DB_CONFIG = {
    'dbname': os.getenv('DB_NAME', 'testdb'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', '1122qqww$'),
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432')
}

class DatabaseManager:
    def __init__(self, config):
        self.config = config
        self.connection = None

    def connect(self, database=None):
        """Establish a connection to the database"""
        db_to_connect = database if database else self.config['dbname']
        try:
            self.connection = psycopg2.connect(
                dbname=db_to_connect,
                user=self.config['user'],
                password=self.config['password'],
                host=self.config['host'],
                port=self.config['port']
            )
            return self.connection
        except OperationalError as e:
            flash(f"Database connection error: {e}", 'error')
            raise

    def create_database(self):
        """Create the database if it doesn't exist"""
        try:
            conn = self.connect("postgres")  # Connect to default database
            conn.autocommit = True
            cur = conn.cursor()
            
            # Check if database exists
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (self.config['dbname'],))
            exists = cur.fetchone()
            
            if not exists:
                cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(self.config['dbname'])))
                print(f"Database '{self.config['dbname']}' created successfully.")
            else:
                print(f"Database '{self.config['dbname']}' already exists.")
                
            cur.close()
        except Exception as e:
            print(f"Error creating database: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def create_tables(self):
        """Create necessary tables with proper constraints"""
        try:
            conn = self.connect()
            cur = conn.cursor()
            
            # Drop existing tables if they exist (for clean setup)
            cur.execute("DROP TABLE IF EXISTS posts CASCADE;")
            cur.execute("DROP TABLE IF EXISTS users CASCADE;")
            
            # Create users table
            cur.execute("""
                CREATE TABLE users (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    email VARCHAR(100) UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status VARCHAR(20) DEFAULT 'active'
                );
            """)
            
            # Create posts table with foreign key constraint
            cur.execute("""
                CREATE TABLE posts (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    title VARCHAR(200) NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    views INTEGER DEFAULT 0
                );
            """)
            
            # Create indexes for better performance
            cur.execute("CREATE INDEX idx_users_email ON users(email);")
            cur.execute("CREATE INDEX idx_posts_user_id ON posts(user_id);")
            cur.execute("CREATE INDEX idx_posts_views ON posts(views);")
            
            conn.commit()
            print("Tables created successfully.")
        except Exception as e:
            print(f"Error creating tables: {e}")
            conn.rollback()
            raise
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

    def get_stats(self):
        """Get database statistics for dashboard"""
        try:
            conn = self.connect()
            cur = conn.cursor()
            
            stats = {}
            
            # Get user count
            cur.execute("SELECT COUNT(*) FROM users;")
            stats['user_count'] = cur.fetchone()[0]
            
            # Get post count
            cur.execute("SELECT COUNT(*) FROM posts;")
            stats['post_count'] = cur.fetchone()[0]
            
            # Get today's activity
            cur.execute("""
                SELECT COUNT(*) FROM (
                    SELECT id FROM users WHERE created_at >= CURRENT_DATE
                    UNION ALL
                    SELECT id FROM posts WHERE created_at >= CURRENT_DATE
                ) AS activity;
            """)
            stats['today_activity'] = cur.fetchone()[0]
            
            # Get most active user
            cur.execute("""
                SELECT u.name, COUNT(p.id) as post_count 
                FROM users u
                JOIN posts p ON u.id = p.user_id
                GROUP BY u.id
                ORDER BY post_count DESC
                LIMIT 1;
            """)
            most_active = cur.fetchone()
            stats['most_active_user'] = most_active[0] if most_active else None
            stats['most_active_posts'] = most_active[1] if most_active else 0
            
            return stats
        except Exception as e:
            print(f"Error getting stats: {e}")
            return None
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

    def insert_user(self, name, email):
        """Insert a new user into the database"""
        try:
            conn = self.connect()
            cur = conn.cursor()
            
            cur.execute("""
                INSERT INTO users (name, email)
                VALUES (%s, %s)
                RETURNING id;
            """, (name, email.lower()))
            
            user_id = cur.fetchone()[0]
            conn.commit()
            return user_id
        except psycopg2.IntegrityError:
            raise ValueError(f"User with email '{email}' already exists.")
        except Exception as e:
            conn.rollback()
            raise Exception(f"Error inserting user: {e}")
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

    def insert_post(self, user_id, title, content):
        """Insert a new post for a user"""
        try:
            conn = self.connect()
            cur = conn.cursor()
            
            cur.execute("""
                INSERT INTO posts (user_id, title, content)
                VALUES (%s, %s, %s)
                RETURNING id;
            """, (user_id, title, content))
            
            post_id = cur.fetchone()[0]
            conn.commit()
            return post_id
        except Exception as e:
            conn.rollback()
            raise Exception(f"Error inserting post: {e}")
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

    def delete_user(self, email):
        """Delete a user by email"""
        try:
            conn = self.connect()
            cur = conn.cursor()
            
            # First check if user exists
            cur.execute("SELECT id, name FROM users WHERE email = %s;", (email.lower(),))
            user = cur.fetchone()
            
            if not user:
                raise ValueError(f"No user found with email '{email}'")
                
            # Delete user (posts will be deleted automatically due to CASCADE)
            cur.execute("DELETE FROM users WHERE email = %s RETURNING id;", (email.lower(),))
            deleted_id = cur.fetchone()[0]
            
            conn.commit()
            return deleted_id
        except Exception as e:
            conn.rollback()
            raise Exception(f"Error deleting user: {e}")
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

    def get_all_users(self, page=1, per_page=10):
        """Get paginated list of users with post counts"""
        try:
            conn = self.connect()
            cur = conn.cursor()
            
            offset = (page - 1) * per_page
            
            # Get users for current page
            cur.execute("""
                SELECT u.id, u.name, u.email, u.created_at, 
                       COUNT(p.id) as post_count
                FROM users u
                LEFT JOIN posts p ON u.id = p.user_id
                GROUP BY u.id
                ORDER BY u.created_at DESC
                LIMIT %s OFFSET %s;
            """, (per_page, offset))
            
            users = cur.fetchall()
            
            # Get total count for pagination
            cur.execute("SELECT COUNT(*) FROM users;")
            total_users = cur.fetchone()[0]
            total_pages = math.ceil(total_users / per_page)
            
            return {
                'users': users,
                'total_users': total_users,
                'total_pages': total_pages,
                'current_page': page
            }
        except Exception as e:
            raise Exception(f"Error fetching users: {e}")
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

    def get_posts_for_user(self, user_id):
        """Get all posts for a specific user"""
        try:
            conn = self.connect()
            cur = conn.cursor()
            
            cur.execute("""
                SELECT id, title, content, created_at, views
                FROM posts
                WHERE user_id = %s
                ORDER BY created_at DESC;
            """, (user_id,))
            
            posts = cur.fetchall()
            return posts
        except Exception as e:
            raise Exception(f"Error fetching posts: {e}")
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

# Initialize database manager
db_manager = DatabaseManager(DB_CONFIG)

# Create DB and tables on start
try:
    db_manager.create_database()
    db_manager.create_tables()
    
    # Add some test data if database is empty (for demo purposes)
    conn = db_manager.connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users;")
    if cur.fetchone()[0] == 0:
        from faker import Faker
        fake = Faker()
        
        # Add 10 demo users with posts
        for _ in range(10):
            name = fake.name()
            email = fake.email()
            user_id = db_manager.insert_user(name, email)
            
            # Add 1-5 posts per user
            for _ in range(fake.random_int(min=1, max=5)):
                db_manager.insert_post(user_id, fake.sentence(), fake.paragraph())
        
        print("Added demo data successfully")
    cur.close()
    conn.close()
except Exception as e:
    print(f"Failed to initialize database: {e}")
    exit(1)

@app.context_processor
def utility_processor():
    def format_datetime(value, format='%b %d, %Y at %H:%M'):
        if value is None:
            return ""
        return value.strftime(format)
    
    def get_posts_for_user(user_id):
        try:
            return db_manager.get_posts_for_user(user_id)
        except:
            return []
    
    return dict(
        format_datetime=format_datetime,
        get_posts_for_user=get_posts_for_user
    )

@app.route('/')
def home():
    stats = db_manager.get_stats()
    return render_template('home.html', stats=stats)

@app.route('/api/stats')
def api_stats():
    stats = db_manager.get_stats()
    return jsonify(stats)

@app.route('/insert', methods=['GET', 'POST'])
def insert():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        
        if not all([name, email, title, content]):
            flash('All fields are required!', 'error')
            return redirect(url_for('insert'))
        
        try:
            user_id = db_manager.insert_user(name, email)
            db_manager.insert_post(user_id, title, content)
            flash('User and post added successfully!', 'success')
            return redirect(url_for('list_users'))
        except ValueError as e:
            flash(str(e), 'error')
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'error')
        
        return redirect(url_for('insert'))
    
    return render_template('form.html')

@app.route('/delete', methods=['GET', 'POST'])
def delete():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        
        if not email:
            flash('Email is required!', 'error')
            return redirect(url_for('delete'))
        
        try:
            deleted_id = db_manager.delete_user(email)
            flash(f'User with email "{email}" and all their posts deleted successfully!', 'success')
            return redirect(url_for('list_users'))
        except ValueError as e:
            flash(str(e), 'error')
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'error')
        
        return redirect(url_for('delete'))
    
    return render_template('delete.html')

@app.route('/users')
@app.route('/users/<int:page>')
def list_users(page=1):
    try:
        per_page = 10
        users_data = db_manager.get_all_users(page, per_page)
        return render_template('users.html', **users_data)
    except Exception as e:
        flash(f'Error fetching users: {str(e)}', 'error')
        return redirect(url_for('home'))

@app.route('/user/<int:user_id>')
def user_detail(user_id):
    try:
        conn = db_manager.connect()
        cur = conn.cursor()
        
        # Get user info
        cur.execute("""
            SELECT id, name, email, created_at, status
            FROM users
            WHERE id = %s;
        """, (user_id,))
        user = cur.fetchone()
        
        if not user:
            flash('User not found!', 'error')
            return redirect(url_for('list_users'))
        
        # Get user's posts
        posts = db_manager.get_posts_for_user(user_id)
        
        return render_template('user_detail.html', user=user, posts=posts)
    except Exception as e:
        flash(f'Error fetching user details: {str(e)}', 'error')
        return redirect(url_for('list_users'))
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)