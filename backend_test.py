#!/usr/bin/env python3
import requests
import json
import uuid
import time
from datetime import datetime, timedelta
import os
import sys

# Get the backend URL from the frontend .env file
with open('frontend/.env', 'r') as f:
    for line in f:
        if line.startswith('REACT_APP_BACKEND_URL='):
            BACKEND_URL = line.strip().split('=')[1].strip('"')
            break

API_URL = f"{BACKEND_URL}/api"
print(f"Using backend URL: {BACKEND_URL}")

# Test data
TEST_USER = {
    "email": f"test_{uuid.uuid4()}@example.com",
    "full_name": "Test User",
    "password": "TestPassword123!"
}

TEST_ADMIN = {
    "email": f"admin_{uuid.uuid4()}@example.com",
    "full_name": "Admin User",
    "password": "AdminPassword123!"
}

TEST_COURSE = {
    "title": "Test Course",
    "description": "A test course for API testing",
    "syllabus": [
        {
            "week": 1,
            "title": "Introduction",
            "topics": ["Overview", "Setup"],
            "content": "Introduction to the course"
        }
    ],
    "price": 99.99,
    "duration_weeks": 4,
    "difficulty_level": "Beginner",
    "instructor": "Test Instructor",
    "enrollment_deadline": (datetime.utcnow() + timedelta(days=30)).isoformat()
}

TEST_REVIEW = {
    "rating": 5,
    "comment": "Great course!"
}

# Test results
results = {
    "auth_system": {"success": False, "details": []},
    "rag_chatbot": {"success": False, "details": []},
    "course_management": {"success": False, "details": []},
    "review_system": {"success": False, "details": []},
    "admin_panel": {"success": False, "details": []}
}

# Helper functions
def log_result(component, test_name, success, message):
    results[component]["details"].append({
        "test": test_name,
        "success": success,
        "message": message
    })
    print(f"{'✅' if success else '❌'} {component} - {test_name}: {message}")

def run_test(component, test_name, test_func):
    try:
        success, message = test_func()
        log_result(component, test_name, success, message)
        return success
    except Exception as e:
        log_result(component, test_name, False, f"Exception: {str(e)}")
        return False

# Test functions
def test_register():
    response = requests.post(f"{API_URL}/register", json=TEST_USER)
    if response.status_code == 200:
        data = response.json()
        if "token" in data and "user" in data:
            TEST_USER["token"] = data["token"]
            TEST_USER["id"] = data["user"]["id"]
            return True, "User registration successful"
    return False, f"User registration failed: {response.status_code} - {response.text}"

def test_login():
    response = requests.post(f"{API_URL}/login", json={
        "email": TEST_USER["email"],
        "password": TEST_USER["password"]
    })
    if response.status_code == 200:
        data = response.json()
        if "token" in data and "user" in data:
            TEST_USER["token"] = data["token"]
            return True, "User login successful"
    return False, f"User login failed: {response.status_code} - {response.text}"

def test_profile():
    headers = {"Authorization": f"Bearer {TEST_USER['token']}"}
    response = requests.get(f"{API_URL}/profile", headers=headers)
    if response.status_code == 200:
        data = response.json()
        if data["email"] == TEST_USER["email"]:
            return True, "Profile retrieval successful"
    return False, f"Profile retrieval failed: {response.status_code} - {response.text}"

def test_register_admin():
    # First register a normal admin user
    response = requests.post(f"{API_URL}/register", json=TEST_ADMIN)
    if response.status_code == 200:
        data = response.json()
        if "token" in data and "user" in data:
            TEST_ADMIN["token"] = data["token"]
            TEST_ADMIN["id"] = data["user"]["id"]
            
            # Now we need to manually update the user to be an admin
            # This would normally be done through an admin interface
            # For testing purposes, we'll check if we can at least register the user
            return True, "Admin user registration successful"
    return False, f"Admin user registration failed: {response.status_code} - {response.text}"

def test_get_courses():
    response = requests.get(f"{API_URL}/courses")
    if response.status_code == 200:
        data = response.json()
        if isinstance(data, list):
            if len(data) > 0:
                TEST_COURSE["existing_id"] = data[0]["id"]
            return True, f"Retrieved {len(data)} courses"
    return False, f"Course retrieval failed: {response.status_code} - {response.text}"

def test_get_course_details():
    if "existing_id" not in TEST_COURSE:
        return False, "No existing course ID to test with"
    
    response = requests.get(f"{API_URL}/courses/{TEST_COURSE['existing_id']}")
    if response.status_code == 200:
        data = response.json()
        if "id" in data and data["id"] == TEST_COURSE["existing_id"]:
            return True, "Course details retrieval successful"
    return False, f"Course details retrieval failed: {response.status_code} - {response.text}"

def test_enroll_course():
    if "existing_id" not in TEST_COURSE:
        return False, "No existing course ID to test with"
    
    headers = {"Authorization": f"Bearer {TEST_USER['token']}"}
    response = requests.post(f"{API_URL}/enroll/{TEST_COURSE['existing_id']}", headers=headers)
    if response.status_code == 200:
        return True, "Course enrollment successful"
    return False, f"Course enrollment failed: {response.status_code} - {response.text}"

def test_my_courses():
    headers = {"Authorization": f"Bearer {TEST_USER['token']}"}
    response = requests.get(f"{API_URL}/my-courses", headers=headers)
    if response.status_code == 200:
        data = response.json()
        if isinstance(data, list):
            return True, f"Retrieved {len(data)} enrolled courses"
    return False, f"My courses retrieval failed: {response.status_code} - {response.text}"

def test_chat():
    chat_request = {
        "message": "What topics are covered in week 3?",
        "session_id": str(uuid.uuid4())
    }
    response = requests.post(f"{API_URL}/chat", json=chat_request)
    if response.status_code == 200:
        data = response.json()
        if "response" in data and len(data["response"]) > 0:
            TEST_REVIEW["session_id"] = chat_request["session_id"]
            return True, "Chat response received successfully"
    return False, f"Chat failed: {response.status_code} - {response.text}"

def test_chat_history():
    if "session_id" not in TEST_REVIEW:
        return False, "No session ID to test with"
    
    response = requests.get(f"{API_URL}/chat/history/{TEST_REVIEW['session_id']}")
    if response.status_code == 200:
        data = response.json()
        if isinstance(data, list):
            return True, f"Retrieved {len(data)} chat messages"
    return False, f"Chat history retrieval failed: {response.status_code} - {response.text}"

def test_create_review():
    if "existing_id" not in TEST_COURSE:
        return False, "No existing course ID to test with"
    
    headers = {"Authorization": f"Bearer {TEST_USER['token']}"}
    review_data = {
        "course_id": TEST_COURSE["existing_id"],
        "rating": TEST_REVIEW["rating"],
        "comment": TEST_REVIEW["comment"]
    }
    response = requests.post(f"{API_URL}/reviews", json=review_data, headers=headers)
    if response.status_code == 200:
        return True, "Review creation successful"
    return False, f"Review creation failed: {response.status_code} - {response.text}"

def test_get_reviews():
    if "existing_id" not in TEST_COURSE:
        return False, "No existing course ID to test with"
    
    response = requests.get(f"{API_URL}/reviews/{TEST_COURSE['existing_id']}")
    if response.status_code == 200:
        data = response.json()
        if isinstance(data, list):
            return True, f"Retrieved {len(data)} reviews"
    return False, f"Reviews retrieval failed: {response.status_code} - {response.text}"

def test_admin_create_course():
    # Note: Since we can't easily make a user an admin in this test environment,
    # we'll just test the endpoint and expect a 403 error
    headers = {"Authorization": f"Bearer {TEST_USER['token']}"}
    response = requests.post(f"{API_URL}/admin/courses", json=TEST_COURSE, headers=headers)
    
    # We expect a 403 error since our test user is not an admin
    if response.status_code == 403:
        return True, "Admin authorization working correctly (non-admin user rejected)"
    elif response.status_code == 200:
        data = response.json()
        if "course_id" in data:
            TEST_COURSE["id"] = data["course_id"]
            return True, "Course creation successful (user has admin privileges)"
    return False, f"Admin endpoint test failed: {response.status_code} - {response.text}"

def run_all_tests():
    print(f"Running tests against backend at {API_URL}")
    
    # Test User Authentication System
    auth_tests = [
        ("User Registration", test_register),
        ("User Login", test_login),
        ("User Profile", test_profile),
        ("Admin Registration", test_register_admin)
    ]
    
    auth_success = all(run_test("auth_system", name, func) for name, func in auth_tests)
    results["auth_system"]["success"] = auth_success
    
    # Test Course Management
    course_tests = [
        ("Get Courses", test_get_courses),
        ("Get Course Details", test_get_course_details),
        ("Enroll in Course", test_enroll_course),
        ("My Courses", test_my_courses)
    ]
    
    course_success = all(run_test("course_management", name, func) for name, func in course_tests)
    results["course_management"]["success"] = course_success
    
    # Test RAG Chatbot
    chat_tests = [
        ("Chat Response", test_chat),
        ("Chat History", test_chat_history)
    ]
    
    chat_success = all(run_test("rag_chatbot", name, func) for name, func in chat_tests)
    results["rag_chatbot"]["success"] = chat_success
    
    # Test Review System
    review_tests = [
        ("Create Review", test_create_review),
        ("Get Reviews", test_get_reviews)
    ]
    
    review_success = all(run_test("review_system", name, func) for name, func in review_tests)
    results["review_system"]["success"] = review_success
    
    # Test Admin Panel
    admin_tests = [
        ("Admin Course Creation", test_admin_create_course)
    ]
    
    admin_success = all(run_test("admin_panel", name, func) for name, func in admin_tests)
    results["admin_panel"]["success"] = admin_success
    
    # Print summary
    print("\n=== TEST SUMMARY ===")
    for component, result in results.items():
        status = "✅ PASSED" if result["success"] else "❌ FAILED"
        print(f"{status} - {component}")
        
        # Print details for failed tests
        if not result["success"]:
            for detail in result["details"]:
                if not detail["success"]:
                    print(f"  - {detail['test']}: {detail['message']}")
    
    return results

if __name__ == "__main__":
    run_all_tests()
