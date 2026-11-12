import os
import jwt
from functools import wraps
from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_cors import CORS
from database import execute_query, init_connection_pool, init_db
from merchant_payments import init_merchant_payment_routes
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# OWASP ZAP 10020: prevent clickjacking via cross-site framing.
# OWASP ZAP 10021: disable MIME type sniffing.
@app.after_request
def add_security_headers(response):
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
JWT_SECRET = os.getenv('JWT_SECRET')

if not app.config['SECRET_KEY']:
    raise RuntimeError("SECRET_KEY environment variable is required")

if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET environment variable is required")


# Register merchant pages and payment API routes before the first request.
init_merchant_payment_routes(app)


# ============================================================
# Authentication decorator
# ============================================================

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):

        token = request.cookies.get('token')

        if not token:
            auth_header = request.headers.get('Authorization')

            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header.split(' ', 1)[1]

        if not token:
            return jsonify({
                'status': 'error',
                'message': 'Authentication required'
            }), 401

        try:
            data = jwt.decode(
                token,
                JWT_SECRET,
                algorithms=['HS256']
            )

            current_user = {
                'user_id': data['user_id'],
                'username': data.get('username')
            }

        except jwt.ExpiredSignatureError:
            return jsonify({
                'status': 'error',
                'message': 'Token expired'
            }), 401

        except jwt.InvalidTokenError:
            return jsonify({
                'status': 'error',
                'message': 'Invalid token'
            }), 401

        return f(current_user, *args, **kwargs)

    return decorated


# ============================================================
# Health check
# ============================================================

@app.route('/healthz')
def healthz():
    return jsonify({
        'status': 'healthy'
    }), 200


# ============================================================
# Home
# ============================================================

@app.route('/')
def index():
    return render_template('index.html')


# ============================================================
# Customer registration page
# ============================================================

@app.route('/register', methods=['GET'])
def register():
    return render_template('register.html')


# ============================================================
# Login
# ============================================================

@app.route('/login', methods=['POST'])
def login():

    data = request.get_json() or {}

    username = data.get('username', '')
    password = data.get('password', '')

    if not username or not password:
        return jsonify({
            'status': 'error',
            'message': 'Username and password are required'
        }), 400

    # SECURITY FIX V1:
    # Use parameterized SQL queries instead of string concatenation.
    query = """
        SELECT id, username, password, account_number, balance, is_admin
        FROM users
        WHERE username = %s AND password = %s
    """

    user = execute_query(
        query,
        (username, password)
    )

    if not user:
        return jsonify({
            'status': 'error',
            'message': 'Invalid username or password'
        }), 401

    user = user[0]

    token = jwt.encode(
        {
            'user_id': user[0],
            'username': user[1],
            'is_admin': user[5]
        },
        JWT_SECRET,
        algorithm='HS256'
    )

    response = jsonify({
        'status': 'success',
        'message': 'Login successful',
        'user': {
            'id': user[0],
            'username': user[1],
            'account_number': user[3],
            'balance': user[4],
            'is_admin': user[5]
        }
    })

    response.set_cookie(
        'token',
        token,
        httponly=True,
        secure=False,
        samesite='Lax'
    )

    return response


# ============================================================
# Logout
# ============================================================

@app.route('/logout', methods=['POST'])
def logout():

    response = jsonify({
        'status': 'success',
        'message': 'Logged out successfully'
    })

    response.delete_cookie('token')

    return response


# ============================================================
# Current user
# ============================================================

@app.route('/me')
@token_required
def current_user(current_user):

    user = execute_query(
        """
        SELECT id, username, account_number, balance, is_admin
        FROM users
        WHERE id = %s
        """,
        (current_user['user_id'],)
    )

    if not user:
        return jsonify({
            'status': 'error',
            'message': 'User not found'
        }), 404

    user = user[0]

    return jsonify({
        'status': 'success',
        'user': {
            'id': user[0],
            'username': user[1],
            'account_number': user[2],
            'balance': user[3],
            'is_admin': user[4]
        }
    })


# ============================================================
# Account balance
# ============================================================

@app.route('/check_balance/<account_number>')
@token_required
def check_balance(current_user, account_number):

    # SECURITY FIX V2:
    # Require authentication and verify that the requested
    # account belongs to the authenticated user.

    user = execute_query(
        """
        SELECT id, username, balance
        FROM users
        WHERE account_number = %s
        """,
        (account_number,)
    )

    if not user:
        return jsonify({
            'status': 'error',
            'message': 'Account not found'
        }), 404

    # Authorization check
    if user[0][0] != current_user['user_id']:
        return jsonify({
            'status': 'error',
            'message': 'Forbidden'
        }), 403

    return jsonify({
        'status': 'success',
        'username': user[0][1],
        'balance': user[0][2],
        'account_number': account_number
    })


# ============================================================
# Update biography
# ============================================================

@app.route('/update_bio', methods=['POST'])
@token_required
def update_bio(current_user):

    data = request.get_json() or {}

    bio = data.get('bio', '')

    if len(bio) > 1000:
        return jsonify({
            'status': 'error',
            'message': 'Biography is too long'
        }), 400

    execute_query(
        """
        UPDATE users
        SET bio = %s
        WHERE id = %s
        """,
        (bio, current_user['user_id']),
        fetch=False
    )

    return jsonify({
        'status': 'success',
        'message': 'Biography updated successfully'
    })


# ============================================================
# Get profile
# ============================================================

@app.route('/profile')
@token_required
def profile(current_user):

    user = execute_query(
        """
        SELECT id, username, account_number, balance, bio, is_admin
        FROM users
        WHERE id = %s
        """,
        (current_user['user_id'],)
    )

    if not user:
        return jsonify({
            'status': 'error',
            'message': 'User not found'
        }), 404

    user = user[0]

    return jsonify({
        'status': 'success',
        'user': {
            'id': user[0],
            'username': user[1],
            'account_number': user[2],
            'balance': user[3],
            'bio': user[4],
            'is_admin': user[5]
        }
    })


# ============================================================
# Admin users
# ============================================================

@app.route('/admin/users')
@token_required
def admin_users(current_user):

    if not current_user.get('is_admin'):
        return jsonify({
            'status': 'error',
            'message': 'Forbidden'
        }), 403

    users = execute_query(
        """
        SELECT id, username, account_number, balance, is_admin
        FROM users
        """
    )

    return jsonify({
        'status': 'success',
        'users': [
            {
                'id': user[0],
                'username': user[1],
                'account_number': user[2],
                'balance': user[3],
                'is_admin': user[4]
            }
            for user in users
        ]
    })


# ============================================================
# Database initialization
# ============================================================

@app.before_request
def initialize_database():

    if not getattr(app, '_db_initialized', False):

        try:
            init_connection_pool()
            init_db()
            app._db_initialized = True

        except Exception as e:
            app.logger.error(
                "Database initialization failed: %s",
                e
            )


# ============================================================
# Error handlers
# ============================================================

@app.errorhandler(404)
def not_found(error):

    return jsonify({
        'status': 'error',
        'message': 'Resource not found'
    }), 404


@app.errorhandler(500)
def internal_error(error):

    app.logger.exception(
        "Internal server error: %s",
        error
    )

    return jsonify({
        'status': 'error',
        'message': 'Internal server error'
    }), 500


# ============================================================
# Application entry point
# ============================================================

if __name__ == '__main__':

    port = int(os.getenv('PORT', 5000))

    app.run(
        host='0.0.0.0',
        port=port,
        debug=False
    )
