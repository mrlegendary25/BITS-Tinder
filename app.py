from flask import Flask, render_template, redirect, url_for, session, request, jsonify
from functools import wraps
from authlib.integrations.flask_client import OAuth
import os
from supabase import create_client
import json
import time
from werkzeug.utils import secure_filename
import io
import mimetypes 
from PIL import Image
app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Change this to a secure secret key

# OAuth Setup
oauth = OAuth(app)

google = oauth.register(





)

# Supabase Configuration
supabase = create_client(


)

def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return function(*args, **kwargs)
    return wrapper

@app.route('/')
def index():
    try:
        # Get count of users
        users_response = supabase.table('users').select('*', count='exact').execute()
        users_count = users_response.count if users_response else 0
        
        # Get count of swipes
        swipes_response = supabase.table('swipes').select('*', count='exact').execute()
        swipes_count = swipes_response.count if swipes_response else 0
        
    except Exception as e:
        print(f"Error fetching counts: {e}")
        users_count = 0
        swipes_count = 0
    
    return render_template('login.html', 
                         users_count=users_count,
                         swipes_count=swipes_count)

@app.route('/login/google')
def google_login():
    redirect_uri = url_for('google_authorize', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/login/google/callback')
def google_authorize():
    token = google.authorize_access_token()
    resp = google.get('https://www.googleapis.com/oauth2/v3/userinfo')
    user_info = resp.json()
    email = user_info['email']
    
    # Check if email is from allowed domain
    if not email.endswith('@hyderabad.bits-pilani.ac.in'):
        return redirect(url_for('index'))
    
    # Check if user exists
    result = supabase.table('users').select('*').eq('email', email).execute()
    
    if len(result.data) > 0:
        session['user'] = {
            'email': email,
            'name': user_info['name'],
            **result.data[0]
        }
        if 'profile_complete' in result.data[0] and result.data[0]['profile_complete']:
            return redirect(url_for('browse'))
        return redirect(url_for('complete_profile'))
    else:
        user_data = {
            'email': email,
            'name': user_info['name'],
            'profile_complete': False
        }
        supabase.table('users').insert(user_data).execute()
        session['user'] = user_data
        return redirect(url_for('complete_profile'))


@app.route('/browse')
@login_required
def browse():
    try:
        # First get current user's full details including gender
        current_user = supabase.table('users')\
            .select('id, gender')\
            .eq('email', session['user']['email'])\
            .execute()
        
        current_user_id = current_user.data[0]['id']
        current_user_gender = current_user.data[0]['gender']
        
        # Determine target gender (opposite of current user's gender)
        target_gender = 'female' if current_user_gender == 'male' else 'male'
        
        # Call the RPC function with both parameters
        profiles = supabase.rpc(
            'get_unswiped_profiles',
            {
                'current_user_id': current_user_id,
                'target_gender': target_gender
            }
        ).execute()
        
        print("Filtered profiles:", len(profiles.data))
        
        return render_template('browse.html',
                           profiles=profiles.data,
                           debug_info={
                               'filtered_profiles': len(profiles.data),
                               'current_user': session['user']['email'],
                               'target_gender': target_gender
                           })
    except Exception as e:
        print("Error in browse:", str(e))
        return "Error loading profiles", 500

@app.route('/swipe', methods=['POST'])
@login_required
def swipe():
    try:
        data = request.json
        target_user_id = data['user_id']
        is_like = data['is_like']
        
        # Get current user's ID
        current_user = supabase.table('users')\
            .select('id')\
            .eq('email', session['user']['email'])\
            .execute()
        
        current_user_id = current_user.data[0]['id']
        
        # Record the swipe
        swipe_data = {
            'user_id': current_user_id,
            'target_user_id': target_user_id,
            'is_like': is_like
        }
        
        # Insert swipe record
        supabase.table('swipes').insert(swipe_data).execute()
        
        # If it's a like, check for a match
        if is_like:
            # Check if target user has already liked current user
            mutual_match = supabase.table('swipes')\
                .select('*')\
                .eq('user_id', target_user_id)\
                .eq('target_user_id', current_user_id)\
                .eq('is_like', True)\
                .execute()
            
            if mutual_match.data:
                # Get matched user's details
                matched_user = supabase.table('users')\
                    .select('*')\
                    .eq('id', target_user_id)\
                    .execute()
                
                return jsonify({
                    'match': True,
                    'user': matched_user.data[0]
                })
        
        return jsonify({'match': False})
        
    except Exception as e:
        print("Swipe error:", str(e))
        return jsonify({'error': str(e)}), 500
@app.route('/get-liked-profiles')
@login_required
def get_liked_profiles():
    try:
        # Get current user's ID
        current_user = supabase.table('users')\
            .select('id')\
            .eq('email', session['user']['email'])\
            .execute()
        
        current_user_id = current_user.data[0]['id']
        
        # Get all profiles the user has liked
        liked_profiles = supabase.rpc(
            'get_liked_profiles',
            {
                'current_user_id': current_user_id
            }
        ).execute()
        
        return jsonify(liked_profiles.data)
    except Exception as e:
        print("Error getting liked profiles:", str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/get-matches')
@login_required
def get_matches():
    try:
        # Get current user's ID
        current_user = supabase.table('users')\
            .select('id')\
            .eq('email', session['user']['email'])\
            .execute()
        
        current_user_id = current_user.data[0]['id']
        
        # Get all mutual matches
        matches = supabase.rpc(
            'get_matches',
            {
                'current_user_id': current_user_id
            }
        ).execute()
        
        return jsonify(matches.data)
    except Exception as e:
        print("Error getting matches:", str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

from PIL import Image
import io

def compress_image(file_data: bytes, max_size: int = 800) -> tuple[bytes, str]:
    """
    Compress an image while maintaining aspect ratio.
    Returns compressed image data and mime type.
    """
    # Open the image
    img = Image.open(io.BytesIO(file_data))
    
    # Convert to RGB if necessary
    if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
        bg = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P':
            img = img.convert('RGBA')
        bg.paste(img, mask=img.split()[-1])
        img = bg

    # Calculate new size maintaining aspect ratio
    ratio = min(max_size / img.size[0], max_size / img.size[1])
    if ratio < 1:
        new_size = tuple(int(dim * ratio) for dim in img.size)
        img = img.resize(new_size, Image.Resampling.LANCZOS)

    # Save the compressed image
    output = io.BytesIO()
    img.save(output, format='JPEG', quality=85, optimize=True)
    
    return output.getvalue(), 'image/jpeg'

@app.route('/complete-profile', methods=['GET', 'POST'])
@login_required
def complete_profile():
    if request.method == 'POST':
        try:
            profile_picture_url = None
            
            # Handle file upload
            if 'picture' in request.files:
                file = request.files['picture']
                if file and file.filename:
                    try:
                        # Read file content
                        file_content = file.read()
                        
                        # Compress the image
                        image_data, content_type = compress_image(file_content)
                        
                        # Generate unique filename
                        timestamp = int(time.time())
                        unique_filename = f"{session['user']['email']}_{timestamp}.jpg"
                        
                        # Upload to Supabase storage
                        result = supabase.storage \
                            .from_('profile-pictures') \
                            .upload(
                                unique_filename,
                                image_data,
                                {"content-type": content_type}
                            )
                        
                        # Get the public URL
                        profile_picture_url = supabase.storage \
                            .from_('profile-pictures') \
                            .get_public_url(unique_filename)
                            
                        print("Upload successful, URL:", profile_picture_url)
                        
                    except Exception as e:
                        print("Error processing image:", str(e))
                        print("File info:", {
                            'filename': file.filename,
                            'content_type': file.content_type,
                            'size': len(file_content) if 'file_content' in locals() else 'unknown'
                        })
                        # Continue without image if upload fails
                        pass
            
            # Prepare profile data
            profile_data = {
                'age': int(request.form.get('age')),
                'gender': request.form.get('gender'),
                'phone': request.form.get('phone'),
                'insta_id': request.form.get('insta_id'),
                'description': request.form.get('description'),
                'profile_complete': True,
                'answers': {
                    'q1': request.form.get('q1'),
                    'q2': request.form.get('q2'),
                    'q3': request.form.get('q3'),
                    'q4': request.form.get('q4'),
                    'q5': request.form.get('q5')
                }
            }
            
            if profile_picture_url:
                profile_data['profile_picture_url'] = profile_picture_url
                print("Adding URL to profile data:", profile_picture_url)
            
            # Update user profile
            result = supabase.table('users') \
                    .update(profile_data) \
                    .eq('email', session['user']['email']) \
                    .execute()
            
            # Update session
            session['user'].update(profile_data)
            
            return redirect(url_for('browse'))
            
        except Exception as e:
            print("Error in complete_profile:", str(e))
            return f"Error saving profile: {str(e)}", 500

    # For GET requests, fetch existing profile data
    try:
        user_data = supabase.table('users') \
            .select('*') \
            .eq('email', session['user']['email']) \
            .execute()
        
        # Get the first (and should be only) user record
        user_profile = user_data.data[0] if user_data.data else {}
        
        return render_template('complete_profile.html', profile=user_profile)
    except Exception as e:
        print("Error fetching profile data:", str(e))
        return render_template('complete_profile.html', profile={})

if __name__ == '__main__':
    app.run(debug=True)