import json
import os
import uuid
from typing import Dict, List, Any
# from redis_manager import RedisManager # No longer needed

class RoundRobinQueueManager:
    def __init__(self):
        # self.redis = RedisManager() # No longer needed
        self.user_queue_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'user_queue.json'))
        self.edit_mode_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'edit_mode.json'))
        
    def _read_json_file(self, file_path: str) -> Dict:
        try:
            with open(file_path, 'r') as f:
                content = f.read().strip()
                return json.loads(content) if content else {}
        except FileNotFoundError:
            return {}

    def _write_json_file(self, file_path: str, data: Dict) -> None:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4)

    def generate_job_id(self) -> str:
        """Generate unique job ID"""
        return f"job_{uuid.uuid4().hex[:8]}"

    def process_user_requests(self, user_requests: Dict[str, List[str]], slack_handler=None) -> Dict[str, str]:
        """
        Process multiple requests per user in round-robin fashion
        Enhanced: Checks for existing queue and sends conversational message if pending jobs exist.
        """
        current_processing = {}
        for user_id, requests in user_requests.items():
            if not requests:
                continue
            # Check for existing queue
            existing_queue = self.get_user_queue_status(user_id)
            if existing_queue["pending_count"] > 0 and slack_handler:
                pending_jobs = existing_queue["pending_requests"]
                message = f"Hey! You have {len(pending_jobs)} job request(s) pending:\n"
                for i, job in enumerate(pending_jobs[:3], 1):
                    message += f"{i}. {job[:50]}...\n"
                message += "\n🤔 What would you like to do?\n"
                message += "• Continue with pending requests\n"
                message += "• Discard them and start fresh\n"
                message += "• Process them all together"
                # Post to Slack and wait for user decision (simulate for now)
                slack_handler._post_response(user_id, None, message)
                # In production, would wait for user input before proceeding
                continue
            
            # Mark user as free if not set
            edit_mode = self._read_json_file(self.edit_mode_file)
            user_edit_status = edit_mode.get(user_id, {})
            if "free" not in user_edit_status:
                user_edit_status["free"] = True
                edit_mode[user_id] = user_edit_status
                self._write_json_file(self.edit_mode_file, edit_mode)
            elif user_edit_status.get("free") == False:
                continue

            # First request goes to current processing
            current_processing[user_id] = requests[0]

            # Remaining requests go to queue
            user_queues = self._read_json_file(self.user_queue_file)
            if len(requests) > 1:
                user_queues[user_id] = requests[1:]
            else:
                user_queues.pop(user_id, None)
            self._write_json_file(self.user_queue_file, user_queues)
        return current_processing

    def get_next_request_for_user(self, user_id: str) -> str | None:
        user_queues = self._read_json_file(self.user_queue_file)
        queue = user_queues.get(user_id, [])
        if queue:
            next_request = queue.pop(0)
            if queue:
                user_queues[user_id] = queue
            else:
                user_queues.pop(user_id, None)
            self._write_json_file(self.user_queue_file, user_queues)
            return next_request
        return None

    def mark_user_busy(self, user_id: str) -> None:
        edit_mode = self._read_json_file(self.edit_mode_file)
        user_status = edit_mode.get(user_id, {})
        user_status["free"] = False
        edit_mode[user_id] = user_status
        self._write_json_file(self.edit_mode_file, edit_mode)

    def mark_user_free(self, user_id: str) -> None:
        edit_mode = self._read_json_file(self.edit_mode_file)
        user_status = edit_mode.get(user_id, {})
        user_status["free"] = True
        edit_mode[user_id] = user_status
        self._write_json_file(self.edit_mode_file, edit_mode)

    def get_user_queue_status(self, user_id: str) -> Dict:
        user_queues = self._read_json_file(self.user_queue_file)
        queue = user_queues.get(user_id, [])
        edit_mode = self._read_json_file(self.edit_mode_file)
        user_status = edit_mode.get(user_id, {})
        return {
            "user_id": user_id,
            "pending_requests": queue,
            "pending_count": len(queue),
            "is_free": user_status.get("free", True)
        }

    def get_all_queue_status(self) -> Dict:
        # Not efficient for large scale, but works for JSON file
        return self._read_json_file(self.user_queue_file)

    def clear_user_queue(self, user_id: str) -> None:
        user_queues = self._read_json_file(self.user_queue_file)
        user_queues.pop(user_id, None)
        self._write_json_file(self.user_queue_file, user_queues)

    def clear_all_queues(self) -> None:
        self._write_json_file(self.user_queue_file, {})


# Example usage and testing
def test_round_robin_logic():
    """Test the round-robin queue management"""
    manager = RoundRobinQueueManager()
    
    # Test data
    user_requests = {
        "user1": ["frontend developer", "backend engineer", "data scientist"],
        "user2": ["full stack developer", "mobile developer"],
        "user3": ["DevOps engineer"]
    }
    
    print("🚀 Testing Round-Robin Queue Management")
    print("=" * 50)
    
    # Process initial requests
    current_processing = manager.process_user_requests(user_requests)
    print(f"📋 Current Processing: {current_processing}")
    
    # Get status
    print("\n📊 Queue Status:")
    status = manager.get_all_queue_status()
    for user_id, user_status in status.items():
        print(f"   {user_id}: {user_status}")
    
    # Simulate processing completion and getting next requests
    print("\n🔄 Processing Next Requests:")
    
    # Get next request for user1
    next_req = manager.get_next_request_for_user("user1")
    print(f"   User1 next: {next_req}")
    
    # Get next request for user2
    next_req = manager.get_next_request_for_user("user2")
    print(f"   User2 next: {next_req}")
    
    # Get next request for user3 (should be None)
    next_req = manager.get_next_request_for_user("user3")
    print(f"   User3 next: {next_req}")
    
    # Final status
    print("\n📊 Final Queue Status:")
    status = manager.get_all_queue_status()
    for user_id, user_status in status.items():
        print(f"   {user_id}: {user_status}")


if __name__ == "__main__":
    test_round_robin_logic()
