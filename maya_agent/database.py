# database.py - Complete job drafts database management with enhanced features
import sqlite3
from datetime import datetime, timedelta
import os
import json
import logging
import uuid
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Database configuration
DB_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'database', 'job_drafts.db'))

def ensure_database_directory():
    """Ensure the database directory exists"""
    db_dir = os.path.dirname(DB_FILE)
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
        print(f"✅ Created database directory: {db_dir}")

def create_draft_table():
    """Create the drafts and edit_requests tables if they don't exist"""
    ensure_database_directory()
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Create drafts table with enhanced schema
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT UNIQUE NOT NULL,     -- You supply this
            user_id TEXT NOT NULL,
            username TEXT,
            channel_id TEXT,
            job_title TEXT,
            company TEXT,
            job_type TEXT,
            experience TEXT,
            location TEXT,
            skills TEXT,
            expiration_date TEXT,
            number_of_people TEXT,
            url TEXT,
            city TEXT,
            state TEXT,
            mail TEXT,
            education TEXT,
            description TEXT,
            timestamp TEXT,
            status TEXT DEFAULT 'active',     -- active, deleted, archived
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            tags TEXT,                        -- JSON array of tags
            priority INTEGER DEFAULT 0,      -- Priority level (0-5)
            salary_range TEXT,                -- Salary information
            remote_allowed BOOLEAN DEFAULT 0, -- Remote work flag
            application_count INTEGER DEFAULT 0 -- Track applications
        )
    """)

    # Create edit_requests table for tracking edit workflows
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS edit_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT UNIQUE NOT NULL,
            user_id TEXT NOT NULL,
            username TEXT,
            channel_id TEXT,
            original_job_data TEXT,  -- JSON string of original job data
            original_description TEXT,
            edit_status TEXT DEFAULT 'pending',  -- pending, processing, completed, failed
            timestamp TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            error_message TEXT,
            edit_notes TEXT,         -- Additional notes about the edit
            FOREIGN KEY (job_id) REFERENCES drafts(job_id)
        )
    """)

    # Create job_applications table for tracking applications
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS job_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            applicant_name TEXT,
            applicant_email TEXT,
            applicant_phone TEXT,
            resume_url TEXT,
            cover_letter TEXT,
            application_date TEXT DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'pending',    -- pending, reviewed, accepted, rejected
            notes TEXT,
            FOREIGN KEY (job_id) REFERENCES drafts(job_id)
        )
    """)

    # Create job_views table for analytics
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS job_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            viewer_ip TEXT,
            viewer_location TEXT,
            view_timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            referrer TEXT,
            FOREIGN KEY (job_id) REFERENCES drafts(job_id)
        )
    """)

    # Create indexes for better performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_drafts_user_id ON drafts(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_drafts_timestamp ON drafts(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_drafts_job_type ON drafts(job_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_drafts_location ON drafts(location)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_edit_requests_user_id ON edit_requests(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_edit_requests_job_id ON edit_requests(job_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_edit_requests_status ON edit_requests(edit_status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_applications_job_id ON job_applications(job_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_views_job_id ON job_views(job_id)")

    conn.commit()
    conn.close()
    print("✅ Database tables created/verified successfully")

def insert_draft(job_id, user_id, username, channel_id, job_data, description, status='active'):
    """Insert a new job draft into the database with enhanced data"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # Extract additional fields from job_data if present
        tags = job_data.get('tags', [])
        priority = job_data.get('priority', 0)
        salary_range = job_data.get('salary_range', '')
        remote_allowed = 1 if 'remote' in str(job_data.get('location', '')).lower() else 0

        cursor.execute("""
            INSERT INTO drafts (
                job_id, user_id, username, channel_id, job_title, company, job_type,
                experience, location, skills, expiration_date, number_of_people,
                url, city, state, mail, education, description, timestamp, status,
                tags, priority, salary_range, remote_allowed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id,
            user_id,
            username,
            channel_id,
            job_data.get("job_title"),
            job_data.get("company"),
            job_data.get("job_type"),
            job_data.get("experience"),
            job_data.get("location"),
            job_data.get("skills"),
            job_data.get("expiration_date"),
            str(job_data.get("number_of_people", "")),
            job_data.get("url"),
            job_data.get("city"),
            job_data.get("state"),
            job_data.get("mail"),
            job_data.get("education"),
            description,
            datetime.utcnow().isoformat(),
            status,
            json.dumps(tags) if tags else None,
            priority,
            salary_range,
            remote_allowed
        ))

        conn.commit()
        conn.close()
        print(f"✅ Draft inserted successfully: {job_id}")
        return True
        
    except sqlite3.IntegrityError as e:
        print(f"❌ Draft insertion failed - job_id already exists: {job_id}")
        logger.error(f"Draft insertion integrity error: {e}")
        return False
    except Exception as e:
        print(f"❌ Draft insertion failed: {e}")
        logger.error(f"Draft insertion error: {e}")
        return False

def get_latest_user_draft(user_id):
    """
    Return only the most recent job draft for a user,
    including job_title, company, experience, location, and skills.
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT job_title, company, experience, location, skills
            FROM drafts
            WHERE user_id = ? AND status = 'active'
            ORDER BY timestamp DESC
            LIMIT 1
        """, (user_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            job_title, company, experience, location, skills_raw = row

            # Parse skills
            try:
                skills = json.loads(skills_raw) if skills_raw else []
            except:
                skills = skills_raw.split(",") if skills_raw else []

            return {
                "job_title": job_title,
                "company": company,
                "experience": experience,
                "location": location,
                "skills": skills
            }

        return {}  # No draft found

    except Exception as e:
        print(f"❌ Error fetching draft for user {user_id}: {e}")
        return {}


def update_draft_status(job_id: str, status: str):
    """Update the status of a specific job draft."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE drafts 
            SET status = ?, updated_at = ? 
            WHERE job_id = ?
        """, (status, datetime.utcnow().isoformat(), job_id))

        conn.commit()
        conn.close()
        print(f"✅ Updated status for job_id {job_id} to '{status}'")
        return True
    except Exception as e:
        print(f"❌ Error updating status for job_id {job_id}: {e}")
        return False


def get_draft_by_job_id(job_id):
    """Fetch a single draft using its job_id"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM drafts WHERE job_id = ? AND status = 'active'", (job_id,))
        row = cursor.fetchone()

        if row:
            # Convert row to dictionary using column names
            columns = [desc[0] for desc in cursor.description]
            result = dict(zip(columns, row))
            
            # Parse JSON fields
            if result.get('tags'):
                try:
                    result['tags'] = json.loads(result['tags'])
                except:
                    result['tags'] = []
            
            conn.close()
            return result
        else:
            conn.close()
            return None
            
    except Exception as e:
        print(f"❌ Error fetching draft by job_id {job_id}: {e}")
        logger.error(f"Get draft error: {e}")
        return None

def get_user_drafts(user_id, limit=10, include_deleted=False, filter_criteria=None):
    """Fetch user's job drafts from database with advanced filtering"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Build query conditions
        conditions = ["user_id = ?"]
        params = [user_id]
        
        if not include_deleted:
            conditions.append("status = 'active'")
        
        # Apply additional filters
        if filter_criteria:
            if filter_criteria.get('job_type'):
                conditions.append("job_type = ?")
                params.append(filter_criteria['job_type'])
            
            if filter_criteria.get('location'):
                conditions.append("location LIKE ?")
                params.append(f"%{filter_criteria['location']}%")
            
            if filter_criteria.get('date_from'):
                conditions.append("timestamp >= ?")
                params.append(filter_criteria['date_from'])
            
            if filter_criteria.get('date_to'):
                conditions.append("timestamp <= ?")
                params.append(filter_criteria['date_to'])
            
            if filter_criteria.get('remote_only'):
                conditions.append("remote_allowed = 1")
        
        params.append(limit)
        where_clause = " AND ".join(conditions)
        
        cursor.execute(f"""
            SELECT * FROM drafts 
            WHERE {where_clause}
            ORDER BY timestamp DESC 
            LIMIT ?
        """, params)
        
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        
        conn.close()
        
        # Convert to list of dictionaries with JSON parsing
        drafts = []
        for row in rows:
            draft = dict(zip(columns, row))
            
            # Parse JSON fields
            if draft.get('tags'):
                try:
                    draft['tags'] = json.loads(draft['tags'])
                except:
                    draft['tags'] = []
            
            drafts.append(draft)
        
        return drafts
        
    except Exception as e:
        print(f"❌ Error fetching user drafts for {user_id}: {e}")
        logger.error(f"Get user drafts error: {e}")
        return []

def get_all_user_drafts(user_id):
    """Get all drafts for a user (no limit)"""
    return get_user_drafts(user_id, limit=10000, include_deleted=False)

def update_draft(job_id, user_id, updated_data):
    """Update an existing draft with enhanced field support"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Build dynamic update query based on provided data
        update_fields = []
        values = []
        
        field_mapping = {
            'job_title': 'job_title',
            'company': 'company',
            'job_type': 'job_type',
            'experience': 'experience',
            'location': 'location',
            'skills': 'skills',
            'expiration_date': 'expiration_date',
            'number_of_people': 'number_of_people',
            'url': 'url',
            'city': 'city',
            'state': 'state',
            'mail': 'mail',
            'education': 'education',
            'description': 'description',
            'tags': 'tags',
            'priority': 'priority',
            'salary_range': 'salary_range',
            'remote_allowed': 'remote_allowed'
        }
        
        for key, db_field in field_mapping.items():
            if key in updated_data:
                update_fields.append(f"{db_field} = ?")
                
                # Handle special fields
                if key == 'tags' and isinstance(updated_data[key], list):
                    values.append(json.dumps(updated_data[key]))
                elif key == 'remote_allowed':
                    values.append(1 if updated_data[key] else 0)
                else:
                    values.append(updated_data[key])
        
        if not update_fields:
            print("⚠️ No valid fields to update")
            return False
        
        # Add timestamp update
        update_fields.append("updated_at = ?")
        values.append(datetime.utcnow().isoformat())
        
        # Add WHERE conditions
        values.extend([job_id, user_id])
        
        query = f"""
            UPDATE drafts 
            SET {', '.join(update_fields)}
            WHERE job_id = ? AND user_id = ? AND status = 'active'
        """
        
        cursor.execute(query, values)
        
        if cursor.rowcount > 0:
            conn.commit()
            conn.close()
            print(f"✅ Draft updated successfully: {job_id}")
            return True
        else:
            conn.close()
            print(f"❌ No draft found to update: {job_id}")
            return False
            
    except Exception as e:
        print(f"❌ Error updating draft {job_id}: {e}")
        logger.error(f"Update draft error: {e}")
        return False

def delete_user_draft(job_id, user_id, soft_delete=True):
    """Delete a specific user's draft (soft delete by default)"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        if soft_delete:
            # Soft delete - mark as deleted
            cursor.execute("""
                UPDATE drafts 
                SET status = 'deleted', updated_at = ?
                WHERE job_id = ? AND user_id = ? AND status = 'active'
            """, (datetime.utcnow().isoformat(), job_id, user_id))
        else:
            # Hard delete - actually remove from database
            cursor.execute("""
                DELETE FROM drafts 
                WHERE job_id = ? AND user_id = ?
            """, (job_id, user_id))
        
        if cursor.rowcount > 0:
            conn.commit()
            conn.close()
            delete_type = "soft deleted" if soft_delete else "permanently deleted"
            print(f"✅ Draft {delete_type} successfully: {job_id}")
            return True
        else:
            conn.close()
            print(f"❌ No draft found to delete: {job_id}")
            return False
            
    except Exception as e:
        print(f"❌ Error deleting draft {job_id}: {e}")
        logger.error(f"Delete draft error: {e}")
        return False

def restore_draft(job_id, user_id):
    """Restore a soft-deleted draft"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE drafts 
            SET status = 'active', updated_at = ?
            WHERE job_id = ? AND user_id = ? AND status = 'deleted'
        """, (datetime.utcnow().isoformat(), job_id, user_id))
        
        if cursor.rowcount > 0:
            conn.commit()
            conn.close()
            print(f"✅ Draft restored successfully: {job_id}")
            return True
        else:
            conn.close()
            print(f"❌ No deleted draft found to restore: {job_id}")
            return False
            
    except Exception as e:
        print(f"❌ Error restoring draft {job_id}: {e}")
        logger.error(f"Restore draft error: {e}")
        return False

def archive_old_drafts(days_old=90):
    """Archive drafts older than specified days"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cutoff_date = (datetime.now() - timedelta(days=days_old)).isoformat()
        
        cursor.execute("""
            UPDATE drafts 
            SET status = 'archived', updated_at = ?
            WHERE timestamp < ? AND status = 'active'
        """, (datetime.utcnow().isoformat(), cutoff_date))
        
        archived_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        print(f"✅ Archived {archived_count} old drafts")
        return archived_count
        
    except Exception as e:
        print(f"❌ Error archiving old drafts: {e}")
        logger.error(f"Archive drafts error: {e}")
        return 0

# Edit Requests Functions
def insert_edit_request(job_id, user_id, username, channel_id, job_data, description):
    """Insert an edit request into the database"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO edit_requests (
                job_id, user_id, username, channel_id, original_job_data, 
                original_description, edit_status, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id,
            user_id,
            username,
            channel_id,
            json.dumps(job_data),  # Store job_data as JSON string
            description,
            'pending',
            datetime.utcnow().isoformat()
        ))

        conn.commit()
        conn.close()
        print(f"✅ Edit request inserted successfully: {job_id}")
        return True
        
    except Exception as e:
        print(f"❌ Edit request insertion failed: {e}")
        logger.error(f"Edit request insertion error: {e}")
        return False

def get_edit_request(job_id):
    """Retrieve an edit request by job_id"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM edit_requests WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()

        conn.close()

        if row:
            columns = [desc[0] for desc in cursor.description]
            result = dict(zip(columns, row))
            # Parse the JSON string back to dict
            try:
                result['original_job_data'] = json.loads(result['original_job_data'])
            except:
                result['original_job_data'] = {}
            return result
        else:
            return None
            
    except Exception as e:
        print(f"❌ Error fetching edit request for {job_id}: {e}")
        logger.error(f"Get edit request error: {e}")
        return None

def get_user_edit_requests(user_id, limit=5):
    """Fetch user's edit requests from database"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM edit_requests 
            WHERE user_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (user_id, limit))
        
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        
        conn.close()
        
        # Convert to list of dictionaries
        edit_requests = []
        for row in rows:
            edit_request = dict(zip(columns, row))
            # Parse JSON data
            if edit_request.get('original_job_data'):
                try:
                    edit_request['original_job_data'] = json.loads(edit_request['original_job_data'])
                except:
                    edit_request['original_job_data'] = {}
            edit_requests.append(edit_request)
        
        return edit_requests
        
    except Exception as e:
        print(f"❌ Error fetching edit requests for {user_id}: {e}")
        logger.error(f"Get user edit requests error: {e}")
        return []

def update_edit_status(job_id, status, error_message=None, edit_notes=None):
    """Update the status of an edit request with additional info"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        update_fields = ["edit_status = ?", "timestamp = ?"]
        values = [status, datetime.utcnow().isoformat()]
        
        if status == 'completed':
            update_fields.append("completed_at = ?")
            values.append(datetime.utcnow().isoformat())
        
        if error_message:
            update_fields.append("error_message = ?")
            values.append(error_message)
        
        if edit_notes:
            update_fields.append("edit_notes = ?")
            values.append(edit_notes)
        
        values.append(job_id)

        cursor.execute(f"""
            UPDATE edit_requests 
            SET {', '.join(update_fields)}
            WHERE job_id = ?
        """, values)

        if cursor.rowcount > 0:
            conn.commit()
            conn.close()
            print(f"✅ Edit request status updated: {job_id} -> {status}")
            return True
        else:
            conn.close()
            print(f"❌ No edit request found to update: {job_id}")
            return False
            
    except Exception as e:
        print(f"❌ Error updating edit status for {job_id}: {e}")
        logger.error(f"Update edit status error: {e}")
        return False

def delete_edit_request(job_id):
    """Delete an edit request"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM edit_requests WHERE job_id = ?", (job_id,))
        
        if cursor.rowcount > 0:
            conn.commit()
            conn.close()
            print(f"✅ Edit request deleted successfully: {job_id}")
            return True
        else:
            conn.close()
            print(f"❌ No edit request found to delete: {job_id}")
            return False
            
    except Exception as e:
        print(f"❌ Error deleting edit request for {job_id}: {e}")
        logger.error(f"Delete edit request error: {e}")
        return False

# Search and Filter Functions
def search_drafts_by_title(user_id, search_term, limit=10):
    """Search drafts by job title"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM drafts 
            WHERE user_id = ? AND status = 'active' 
            AND job_title LIKE ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (user_id, f"%{search_term}%", limit))
        
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        conn.close()
        
        return [dict(zip(columns, row)) for row in rows]
        
    except Exception as e:
        print(f"❌ Error searching drafts: {e}")
        logger.error(f"Search drafts error: {e}")
        return []

def search_drafts_advanced(user_id, search_criteria, limit=20):
    """Advanced search with multiple criteria"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        conditions = ["user_id = ?", "status = 'active'"]
        params = [user_id]
        
        if search_criteria.get('title'):
            conditions.append("job_title LIKE ?")
            params.append(f"%{search_criteria['title']}%")
        
        if search_criteria.get('company'):
            conditions.append("company LIKE ?")
            params.append(f"%{search_criteria['company']}%")
        
        if search_criteria.get('skills'):
            conditions.append("skills LIKE ?")
            params.append(f"%{search_criteria['skills']}%")
        
        if search_criteria.get('location'):
            conditions.append("location LIKE ?")
            params.append(f"%{search_criteria['location']}%")
        
        if search_criteria.get('job_type'):
            conditions.append("job_type = ?")
            params.append(search_criteria['job_type'])
        
        if search_criteria.get('remote_only'):
            conditions.append("remote_allowed = 1")
        
        params.append(limit)
        where_clause = " AND ".join(conditions)
        
        cursor.execute(f"""
            SELECT * FROM drafts 
            WHERE {where_clause}
            ORDER BY timestamp DESC 
            LIMIT ?
        """, params)
        
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        conn.close()
        
        return [dict(zip(columns, row)) for row in rows]
        
    except Exception as e:
        print(f"❌ Error in advanced search: {e}")
        logger.error(f"Advanced search error: {e}")
        return []

def get_drafts_by_date_range(user_id, start_date, end_date, limit=50):
    """Get drafts within a date range"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM drafts 
            WHERE user_id = ? AND status = 'active'
            AND timestamp BETWEEN ? AND ?
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (user_id, start_date, end_date, limit))
        
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        conn.close()
        
        return [dict(zip(columns, row)) for row in rows]
        
    except Exception as e:
        print(f"❌ Error getting drafts by date range: {e}")
        logger.error(f"Get drafts by date range error: {e}")
        return []

# Statistics Functions
def get_user_stats(user_id):
    """Get comprehensive statistics for a user"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Total drafts by status
        cursor.execute("SELECT status, COUNT(*) FROM drafts WHERE user_id = ? GROUP BY status", (user_id,))
        status_counts = dict(cursor.fetchall())
        
        # Edit requests
        cursor.execute("SELECT COUNT(*) FROM edit_requests WHERE user_id = ?", (user_id,))
        total_edit_requests = cursor.fetchone()[0]
        
        # Recent drafts (last 30 days)
        thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
        cursor.execute("""
            SELECT COUNT(*) FROM drafts 
            WHERE user_id = ? AND status = 'active' AND timestamp > ?
        """, (user_id, thirty_days_ago))
        recent_drafts = cursor.fetchone()[0]
        
        # Most common job types
        cursor.execute("""
            SELECT job_type, COUNT(*) as count FROM drafts 
            WHERE user_id = ? AND status = 'active' AND job_type IS NOT NULL
            GROUP BY job_type 
            ORDER BY count DESC 
            LIMIT 5
        """, (user_id,))
        job_types = cursor.fetchall()
        
        # Most common locations
        cursor.execute("""
            SELECT location, COUNT(*) as count FROM drafts 
            WHERE user_id = ? AND status = 'active' AND location IS NOT NULL
            GROUP BY location 
            ORDER BY count DESC 
            LIMIT 5
        """, (user_id,))
        locations = cursor.fetchall()
        
        # Remote jobs percentage
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN remote_allowed = 1 THEN 1 ELSE 0 END) as remote_count
            FROM drafts 
            WHERE user_id = ? AND status = 'active'
        """, (user_id,))
        total, remote_count = cursor.fetchone()
        remote_percentage = (remote_count / total * 100) if total > 0 else 0
        
        conn.close()
        
        stats = {
            'total_active_drafts': status_counts.get('active', 0),
            'total_deleted_drafts': status_counts.get('deleted', 0),
            'total_archived_drafts': status_counts.get('archived', 0),
            'total_edit_requests': total_edit_requests,
            'recent_drafts_30_days': recent_drafts,
            'most_common_job_types': [{'type': jt[0], 'count': jt[1]} for jt in job_types],
            'most_common_locations': [{'location': loc[0], 'count': loc[1]} for loc in locations],
            'remote_jobs_percentage': round(remote_percentage, 1),
            'total_jobs_all_status': sum(status_counts.values())
        }
        
        return stats
        
    except Exception as e:
        print(f"❌ Error getting user stats: {e}")
        logger.error(f"Get user stats error: {e}")
        return {
            'total_active_drafts': 0,
            'total_deleted_drafts': 0,
            'total_archived_drafts': 0,
            'total_edit_requests': 0,
            'recent_drafts_30_days': 0,
            'most_common_job_types': [],
            'most_common_locations': [],
            'remote_jobs_percentage': 0,
            'total_jobs_all_status': 0
        }

def get_global_stats():
    """Get global database statistics"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Total jobs by status
        cursor.execute("SELECT status, COUNT(*) FROM drafts GROUP BY status")
        global_status_counts = dict(cursor.fetchall())
        
        # Unique users
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM drafts")
        unique_users = cursor.fetchone()[0]
        
        # Active users (posted in last 30 days)
        thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
        cursor.execute("""
            SELECT COUNT(DISTINCT user_id) FROM drafts 
            WHERE timestamp > ?
        """, (thirty_days_ago,))
        active_users = cursor.fetchone()[0]
        
        # Most popular job types globally
        cursor.execute("""
            SELECT job_type, COUNT(*) as count FROM drafts 
            WHERE status = 'active' AND job_type IS NOT NULL
            GROUP BY job_type 
            ORDER BY count DESC 
            LIMIT 10
        """)
        global_job_types = cursor.fetchall()
        
        # Recent activity (last 7 days)
        seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
        cursor.execute("SELECT COUNT(*) FROM drafts WHERE timestamp > ?", (seven_days_ago,))
        recent_activity = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'global_status_counts': global_status_counts,
            'unique_users': unique_users,
            'active_users_30_days': active_users,
            'global_job_types': [{'type': jt[0], 'count': jt[1]} for jt in global_job_types],
            'recent_activity_7_days': recent_activity,
            'total_jobs_ever': sum(global_status_counts.values())
        }
        
    except Exception as e:
        print(f"❌ Error getting global stats: {e}")
        logger.error(f"Get global stats error: {e}")
        return {}

# Job Applications Functions
def add_job_application(job_id, applicant_data):
    """Add a job application"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO job_applications (
                job_id, applicant_name, applicant_email, applicant_phone,
                resume_url, cover_letter, status, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id,
            applicant_data.get('name'),
            applicant_data.get('email'),
            applicant_data.get('phone'),
            applicant_data.get('resume_url'),
            applicant_data.get('cover_letter'),
            applicant_data.get('status', 'pending'),
            applicant_data.get('notes', '')
        ))
        
        # Update application count in drafts table
        cursor.execute("""
            UPDATE drafts 
            SET application_count = application_count + 1
            WHERE job_id = ?
        """, (job_id,))
        
        conn.commit()
        conn.close()
        print(f"✅ Application added for job: {job_id}")
        return True
        
    except Exception as e:
        print(f"❌ Error adding application: {e}")
        logger.error(f"Add application error: {e}")
        return False

def get_job_applications(job_id, limit=50):
    """Get applications for a specific job"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM job_applications 
            WHERE job_id = ? 
            ORDER BY application_date DESC 
            LIMIT ?
        """, (job_id, limit))
        
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        conn.close()
        
        return [dict(zip(columns, row)) for row in rows]
        
    except Exception as e:
        print(f"❌ Error getting applications: {e}")
        logger.error(f"Get applications error: {e}")
        return []

def update_application_status(application_id, status, notes=None):
    """Update application status"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        update_fields = ["status = ?"]
        values = [status]
        
        if notes:
            update_fields.append("notes = ?")
            values.append(notes)
        
        values.append(application_id)
        
        cursor.execute(f"""
            UPDATE job_applications 
            SET {', '.join(update_fields)}
            WHERE id = ?
        """, values)
        
        conn.commit()
        conn.close()
        print(f"✅ Application status updated: {application_id} -> {status}")
        return True
        
    except Exception as e:
        print(f"❌ Error updating application: {e}")
        logger.error(f"Update application error: {e}")
        return False

# Job Views/Analytics Functions
def record_job_view(job_id, viewer_data):
    """Record a job view for analytics"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO job_views (
                job_id, viewer_ip, viewer_location, referrer
            ) VALUES (?, ?, ?, ?)
        """, (
            job_id,
            viewer_data.get('ip'),
            viewer_data.get('location'),
            viewer_data.get('referrer')
        ))
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Record job view error: {e}")
        return False

def get_job_analytics(job_id):
    """Get analytics for a specific job"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Total views
        cursor.execute("SELECT COUNT(*) FROM job_views WHERE job_id = ?", (job_id,))
        total_views = cursor.fetchone()[0]
        
        # Views by date (last 30 days)
        thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
        cursor.execute("""
            SELECT DATE(view_timestamp) as date, COUNT(*) as views
            FROM job_views 
            WHERE job_id = ? AND view_timestamp > ?
            GROUP BY DATE(view_timestamp)
            ORDER BY date DESC
        """, (job_id, thirty_days_ago))
        views_by_date = cursor.fetchall()
        
        # Application count
        cursor.execute("SELECT application_count FROM drafts WHERE job_id = ?", (job_id,))
        application_count = cursor.fetchone()[0] if cursor.fetchone() else 0
        
        # Application conversion rate
        conversion_rate = (application_count / total_views * 100) if total_views > 0 else 0
        
        conn.close()
        
        return {
            'total_views': total_views,
            'application_count': application_count,
            'conversion_rate': round(conversion_rate, 2),
            'views_by_date': [{'date': d[0], 'views': d[1]} for d in views_by_date]
        }
        
    except Exception as e:
        print(f"❌ Error getting job analytics: {e}")
        logger.error(f"Get job analytics error: {e}")
        return {}

# Database Maintenance Functions
def cleanup_old_edit_requests(days_old=30):
    """Clean up old completed edit requests"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cutoff_date = (datetime.now() - timedelta(days=days_old)).isoformat()
        
        cursor.execute("""
            DELETE FROM edit_requests 
            WHERE edit_status = 'completed' AND timestamp < ?
        """, (cutoff_date,))
        
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        print(f"✅ Cleaned up {deleted_count} old edit requests")
        return deleted_count
        
    except Exception as e:
        print(f"❌ Error cleaning up edit requests: {e}")
        logger.error(f"Cleanup edit requests error: {e}")
        return 0

def cleanup_old_job_views(days_old=365):
    """Clean up old job view records"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cutoff_date = (datetime.now() - timedelta(days=days_old)).isoformat()
        
        cursor.execute("""
            DELETE FROM job_views 
            WHERE view_timestamp < ?
        """, (cutoff_date,))
        
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        print(f"✅ Cleaned up {deleted_count} old job view records")
        return deleted_count
        
    except Exception as e:
        print(f"❌ Error cleaning up job views: {e}")
        logger.error(f"Cleanup job views error: {e}")
        return 0

def get_database_stats():
    """Get overall database statistics"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Count of drafts by status
        cursor.execute("SELECT status, COUNT(*) FROM drafts GROUP BY status")
        draft_counts = dict(cursor.fetchall())
        
        # Count of edit requests by status
        cursor.execute("SELECT edit_status, COUNT(*) FROM edit_requests GROUP BY edit_status")
        edit_counts = dict(cursor.fetchall())
        
        # Count of applications by status
        cursor.execute("SELECT status, COUNT(*) FROM job_applications GROUP BY status")
        application_counts = dict(cursor.fetchall())
        
        # Unique users
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM drafts")
        unique_users = cursor.fetchone()[0]
        
        # Total views
        cursor.execute("SELECT COUNT(*) FROM job_views")
        total_views = cursor.fetchone()[0]
        
        # Recent activity (last 7 days)
        seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
        cursor.execute("SELECT COUNT(*) FROM drafts WHERE timestamp > ?", (seven_days_ago,))
        recent_activity = cursor.fetchone()[0]
        
        # Database size
        cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
        db_size = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'draft_counts': draft_counts,
            'edit_request_counts': edit_counts,
            'application_counts': application_counts,
            'unique_users': unique_users,
            'total_views': total_views,
            'recent_activity_7_days': recent_activity,
            'database_size_bytes': db_size,
            'database_size_mb': round(db_size / (1024*1024), 2)
        }
        
    except Exception as e:
        print(f"❌ Error getting database stats: {e}")
        logger.error(f"Get database stats error: {e}")
        return {}

def optimize_database():
    """Optimize database performance"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Analyze tables for query optimization
        cursor.execute("ANALYZE")
        
        # Vacuum to reclaim space and defragment
        cursor.execute("VACUUM")
        
        conn.commit()
        conn.close()
        
        print("✅ Database optimized successfully")
        return True
        
    except Exception as e:
        print(f"❌ Error optimizing database: {e}")
        logger.error(f"Database optimization error: {e}")
        return False

# Backup and Export Functions
def backup_database(backup_path=None):
    """Create a backup of the database"""
    try:
        if not backup_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{DB_FILE}.backup_{timestamp}"
        
        # Simple file copy backup
        import shutil
        shutil.copy2(DB_FILE, backup_path)
        
        print(f"✅ Database backed up to: {backup_path}")
        return backup_path
        
    except Exception as e:
        print(f"❌ Error backing up database: {e}")
        logger.error(f"Database backup error: {e}")
        return None

def export_user_data_json(user_id):
    """Export all user data as JSON"""
    try:
        user_data = {
            'user_id': user_id,
            'export_timestamp': datetime.utcnow().isoformat(),
            'drafts': get_all_user_drafts(user_id),
            'edit_requests': get_user_edit_requests(user_id, limit=1000),
            'statistics': get_user_stats(user_id)
        }
        
        return json.dumps(user_data, indent=2, default=str)
        
    except Exception as e:
        print(f"❌ Error exporting user data: {e}")
        logger.error(f"Export user data error: {e}")
        return None

# Initialize database on import
def initialize_database():
    """Initialize the database with tables"""
    try:
        create_draft_table()
        print("✅ Database initialized successfully")
        return True
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        logger.error(f"Database initialization error: {e}")
        return False

# Enhanced utility functions
def generate_job_id(user_id=None):
    """Generate a unique job ID"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    
    if user_id:
        return f"job_{user_id}_{timestamp}_{unique_id}"
    else:
        return f"job_{timestamp}_{unique_id}"

def validate_job_data(job_data):
    """Validate job data before insertion"""
    required_fields = ['job_title', 'company']
    
    for field in required_fields:
        if not job_data.get(field):
            return False, f"Missing required field: {field}"
    
    # Validate email format if provided
    email = job_data.get('mail')
    if email and '@' not in email:
        return False, "Invalid email format"
    
    # Validate URL format if provided
    url = job_data.get('url')
    if url and not (url.startswith('http://') or url.startswith('https://')):
        return False, "Invalid URL format"
    
    return True, "Valid"

# Example/Test Functions
def create_sample_data():
    """Create sample data for testing"""
    sample_job_data = {
        "job_title": "AI Research Engineer",
        "company": "whisprnet.ai",
        "job_type": "full-time",
        "experience": "3 years",
        "location": "Remote",
        "skills": "Python, Deep Learning, TensorFlow",
        "expiration_date": "2025-08-01",
        "number_of_people": 2,
        "url": "https://linkedin.com/jobs/ai-engineer",
        "city": "Pondicherry",
        "state": "Pondicherry",
        "mail": "careers@whisprnet.ai",
        "education": "BTech/MTech in CS/AI",
        "tags": ["AI", "Remote", "Senior"],
        "priority": 3,
        "salary_range": "$80,000 - $120,000"
    }

    job_id = generate_job_id("sample_user")
    
    # Insert sample draft
    success = insert_draft(
        job_id=job_id,
        user_id="U123456",
        username="naveen_k",
        channel_id="C123456",
        job_data=sample_job_data,
        description="We are looking for an experienced AI Research Engineer to join our growing team. The ideal candidate will have strong experience in deep learning, Python programming, and working with large language models."
    )
    
    if success:
        print(f"✅ Sample data created successfully! Job ID: {job_id}")
        
        # Add sample application
        sample_applicant = {
            'name': 'John Doe',
            'email': 'john.doe@example.com',
            'phone': '+1-555-0123',
            'resume_url': 'https://example.com/resume.pdf',
            'cover_letter': 'I am interested in this AI position...',
            'status': 'pending'
        }
        add_job_application(job_id, sample_applicant)
        
        # Record sample view
        sample_viewer = {
            'ip': '192.168.1.100',
            'location': 'New York, USA',
            'referrer': 'https://google.com'
        }
        record_job_view(job_id, sample_viewer)
        
    else:
        print("❌ Failed to create sample data")

def test_all_functions():
    """Test all database functions"""
    print("\n" + "="*80)
    print("TESTING ALL DATABASE FUNCTIONS")
    print("="*80)
    
    # Test user
    test_user_id = "test_user_123"
    test_username = "test_user"
    test_channel = "C123TEST"
    
    # Test draft operations
    print("\n1. Testing draft operations...")
    
    test_job_data = {
        "job_title": "Test Developer",
        "company": "Test Company",
        "job_type": "full-time",
        "experience": "2 years",
        "location": "Remote",
        "skills": "Python, Testing",
        "tags": ["Testing", "Remote"],
        "priority": 2,
        "salary_range": "$60,000 - $80,000"
    }
    
    job_id = generate_job_id(test_user_id)
    
    # Insert
    insert_draft(job_id, test_user_id, test_username, test_channel, test_job_data, "Test description")
    
    # Get by ID
    draft = get_draft_by_job_id(job_id)
    print(f"Retrieved draft: {draft.get('job_title') if draft else 'None'}")
    
    # Get user drafts
    user_drafts = get_user_drafts(test_user_id)
    print(f"User has {len(user_drafts)} drafts")
    
    # Update draft
    update_draft(job_id, test_user_id, {"job_title": "Updated Test Developer", "priority": 4})
    
    # Test search
    print("\n2. Testing search functions...")
    search_results = search_drafts_by_title(test_user_id, "Test")
    print(f"Search found {len(search_results)} results")
    
    # Test advanced search
    search_criteria = {'title': 'Test', 'job_type': 'full-time'}
    advanced_results = search_drafts_advanced(test_user_id, search_criteria)
    print(f"Advanced search found {len(advanced_results)} results")
    
    # Test edit requests
    print("\n3. Testing edit requests...")
    insert_edit_request(job_id, test_user_id, test_username, test_channel, test_job_data, "Original description")
    
    edit_req = get_edit_request(job_id)
    print(f"Edit request status: {edit_req.get('edit_status') if edit_req else 'None'}")
    
    # Test applications
    print("\n4. Testing applications...")
    test_applicant = {
        'name': 'Test Applicant',
        'email': 'test@example.com',
        'status': 'pending'
    }
    add_job_application(job_id, test_applicant)
    
    applications = get_job_applications(job_id)
    print(f"Job has {len(applications)} applications")
    
    # Test analytics
    print("\n5. Testing analytics...")
    test_viewer = {'ip': '127.0.0.1', 'location': 'Test City'}
    record_job_view(job_id, test_viewer)
    
    analytics = get_job_analytics(job_id)
    print(f"Job analytics: {analytics}")
    
    # Test statistics
    print("\n6. Testing statistics...")
    stats = get_user_stats(test_user_id)
    print(f"User stats: {stats}")
    
    db_stats = get_database_stats()
    print(f"Database stats: {db_stats}")
    
    # Test export
    print("\n7. Testing export...")
    export_data = export_user_data_json(test_user_id)
    print(f"Export data length: {len(export_data) if export_data else 0} characters")
    
    # Cleanup test data
    print("\n8. Cleaning up test data...")
    delete_user_draft(job_id, test_user_id)
    delete_edit_request(job_id)
    
    print("✅ All tests completed!")

# Performance monitoring
def get_performance_metrics():
    """Get database performance metrics"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Get table sizes
        cursor.execute("""
            SELECT name, 
                   COUNT(*) as row_count
            FROM sqlite_master 
            WHERE type='table' 
            AND name IN ('drafts', 'edit_requests', 'job_applications', 'job_views')
        """)
        
        table_info = {}
        for table_name in ['drafts', 'edit_requests', 'job_applications', 'job_views']:
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            table_info[table_name] = count
        
        # Get index usage stats (simplified)
        cursor.execute("PRAGMA index_list('drafts')")
        index_count = len(cursor.fetchall())
        
        conn.close()
        
        return {
            'table_sizes': table_info,
            'total_records': sum(table_info.values()),
            'index_count': index_count
        }
        
    except Exception as e:
        logger.error(f"Performance metrics error: {e}")
        return {}

# Run initialization when module is imported
if __name__ == "__main__":
    print("Enhanced Database module loaded!")
    print("Initializing database...")
    initialize_database()
    
    # Uncomment to run tests
    # test_all_functions()
    
    # Uncomment to create sample data
    # create_sample_data()
    
    print("\n🌟 AVAILABLE FEATURES:")
    print("• Complete CRUD operations for job drafts")
    print("• Advanced search and filtering")
    print("• Edit request tracking")
    print("• Job applications management") 
    print("• Analytics and view tracking")
    print("• Comprehensive statistics")
    print("• Database maintenance and optimization")
    print("• Data export and backup")
    print("• Performance monitoring")
    
else:
    # Auto-initialize when imported
    initialize_database()