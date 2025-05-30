from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timedelta
import bcrypt
import jwt
from groq import Groq
import json
import asyncio
from bson import ObjectId

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Groq client
groq_client = Groq(api_key=os.environ.get('GROQ_API_KEY'))

# JWT settings
JWT_SECRET = os.environ.get('JWT_SECRET', 'your-secret-key-change-in-production')
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# Create the main app without a prefix
app = FastAPI(title="AI Course Landing Page API")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Security
security = HTTPBearer()

# Models
class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: EmailStr
    full_name: str
    password_hash: str
    is_admin: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    enrolled_courses: List[str] = []
    progress: Dict[str, float] = {}

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Course(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str
    syllabus: List[Dict[str, Any]]
    price: float
    duration_weeks: int
    difficulty_level: str
    instructor: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True
    enrollment_deadline: datetime
    total_enrollments: int = 0
    rating: float = 0.0
    reviews: List[Dict[str, Any]] = []

class CourseCreate(BaseModel):
    title: str
    description: str
    syllabus: List[Dict[str, Any]]
    price: float
    duration_weeks: int
    difficulty_level: str
    instructor: str
    enrollment_deadline: datetime

class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    user_id: Optional[str] = None
    message: str
    response: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class ChatRequest(BaseModel):
    message: str
    session_id: str

class Review(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    course_id: str
    user_id: str
    user_name: str
    rating: int
    comment: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Enrollment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    course_id: str
    enrolled_at: datetime = Field(default_factory=datetime.utcnow)
    progress: float = 0.0
    completed: bool = False
    certificate_issued: bool = False

# Utility functions
def convert_objectid(obj):
    """Convert MongoDB ObjectId to string for JSON serialization"""
    if isinstance(obj, dict):
        return {key: convert_objectid(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_objectid(item) for item in obj]
    elif isinstance(obj, ObjectId):
        return str(obj)
    else:
        return obj

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_jwt_token(user_id: str, is_admin: bool = False) -> str:
    payload = {
        "user_id": user_id,
        "is_admin": is_admin,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = await db.users.find_one({"id": user_id})
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        return User(**user)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_admin_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

# Course content for RAG system
COURSE_CONTENT = {
    "ai_ml_fundamentals": {
        "title": "AI & Machine Learning Fundamentals",
        "description": "Comprehensive course covering artificial intelligence and machine learning from basics to advanced applications",
        "syllabus": [
            {
                "week": 1,
                "title": "Introduction to AI and ML",
                "topics": ["What is AI?", "Types of Machine Learning", "Applications of AI", "Python for ML"],
                "content": "Introduction to artificial intelligence concepts, machine learning paradigms including supervised, unsupervised, and reinforcement learning. Overview of Python programming for machine learning with libraries like NumPy, Pandas, and Scikit-learn."
            },
            {
                "week": 2,
                "title": "Data Preprocessing and Analysis",
                "topics": ["Data Collection", "Data Cleaning", "Feature Engineering", "Exploratory Data Analysis"],
                "content": "Learn to collect, clean, and prepare data for machine learning. Master data preprocessing techniques, handle missing values, outliers, and perform feature engineering for better model performance."
            },
            {
                "week": 3,
                "title": "Supervised Learning Algorithms",
                "topics": ["Linear Regression", "Logistic Regression", "Decision Trees", "Random Forest"],
                "content": "Deep dive into supervised learning algorithms including regression and classification. Understand when to use each algorithm and how to implement them effectively."
            },
            {
                "week": 4,
                "title": "Advanced ML Algorithms",
                "topics": ["Support Vector Machines", "Neural Networks", "Ensemble Methods", "Model Evaluation"],
                "content": "Explore advanced machine learning algorithms including SVMs, neural networks, and ensemble methods. Learn proper model evaluation techniques and metrics."
            },
            {
                "week": 5,
                "title": "Deep Learning Fundamentals",
                "topics": ["Neural Network Architecture", "Backpropagation", "TensorFlow/Keras", "CNN Basics"],
                "content": "Introduction to deep learning with neural networks. Learn to build and train deep learning models using TensorFlow and Keras frameworks."
            },
            {
                "week": 6,
                "title": "Computer Vision with Deep Learning",
                "topics": ["Convolutional Neural Networks", "Image Classification", "Object Detection", "Transfer Learning"],
                "content": "Apply deep learning to computer vision problems. Build CNN models for image classification and object detection using transfer learning techniques."
            },
            {
                "week": 7,
                "title": "Natural Language Processing",
                "topics": ["Text Preprocessing", "Word Embeddings", "RNNs and LSTMs", "Transformer Models"],
                "content": "Explore natural language processing with machine learning. Learn text preprocessing, word embeddings, and implement RNN/LSTM models for text analysis."
            },
            {
                "week": 8,
                "title": "ML Model Deployment and Production",
                "topics": ["Model Deployment", "API Development", "MLOps", "Monitoring and Maintenance"],
                "content": "Learn to deploy machine learning models in production environments. Understand MLOps practices, API development, and model monitoring."
            }
        ],
        "faq": [
            {
                "question": "What prerequisites do I need for this course?",
                "answer": "Basic programming knowledge in Python is recommended. No prior machine learning experience required."
            },
            {
                "question": "How long does it take to complete the course?",
                "answer": "The course is designed to be completed in 8 weeks with 5-10 hours of study per week."
            },
            {
                "question": "Will I get a certificate?",
                "answer": "Yes, you'll receive a certificate of completion after successfully finishing all course modules and projects."
            },
            {
                "question": "What tools and software will I use?",
                "answer": "Python, Jupyter Notebooks, TensorFlow, Keras, Scikit-learn, Pandas, NumPy, and other industry-standard tools."
            },
            {
                "question": "Is there practical project work?",
                "answer": "Yes, each week includes hands-on projects and assignments to reinforce learning concepts."
            }
        ]
    }
}

def get_rag_context(query: str) -> str:
    """Get relevant context for RAG from course content"""
    course_data = COURSE_CONTENT["ai_ml_fundamentals"]
    context_parts = []
    
    # Add course overview
    context_parts.append(f"Course: {course_data['title']}")
    context_parts.append(f"Description: {course_data['description']}")
    
    # Add relevant syllabus content
    query_lower = query.lower()
    for week in course_data['syllabus']:
        if any(topic.lower() in query_lower or query_lower in topic.lower() for topic in week['topics']):
            context_parts.append(f"Week {week['week']}: {week['title']}")
            context_parts.append(f"Topics: {', '.join(week['topics'])}")
            context_parts.append(f"Content: {week['content']}")
    
    # Add relevant FAQ
    for faq in course_data['faq']:
        if query_lower in faq['question'].lower() or query_lower in faq['answer'].lower():
            context_parts.append(f"FAQ - Q: {faq['question']}")
            context_parts.append(f"A: {faq['answer']}")
    
    return "\n\n".join(context_parts)

# API Routes
@api_router.post("/register")
async def register(user_data: UserCreate):
    # Check if user exists
    existing_user = await db.users.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create user
    user = User(
        email=user_data.email,
        full_name=user_data.full_name,
        password_hash=hash_password(user_data.password)
    )
    
    await db.users.insert_one(user.dict())
    
    # Create JWT token
    token = create_jwt_token(user.id, user.is_admin)
    
    return {
        "message": "User registered successfully",
        "token": token,
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "is_admin": user.is_admin
        }
    }

@api_router.post("/login")
async def login(credentials: UserLogin):
    user = await db.users.find_one({"email": credentials.email})
    if not user or not verify_password(credentials.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_jwt_token(user["id"], user["is_admin"])
    
    return {
        "message": "Login successful",
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "is_admin": user["is_admin"]
        }
    }

@api_router.get("/profile")
async def get_profile(current_user: User = Depends(get_current_user)):
    return current_user

@api_router.get("/courses")
async def get_courses():
    try:
        courses = await db.courses.find({"is_active": True}).to_list(100)
        return convert_objectid(courses)
    except Exception as e:
        logger.error(f"Error fetching courses: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching courses")

@api_router.get("/courses/{course_id}")
async def get_course(course_id: str):
    try:
        course = await db.courses.find_one({"id": course_id})
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")
        return convert_objectid(course)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching course: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching course")

@api_router.post("/admin/courses")
async def create_course(course_data: CourseCreate, current_user: User = Depends(get_admin_user)):
    course = Course(**course_data.dict())
    await db.courses.insert_one(course.dict())
    return {"message": "Course created successfully", "course_id": course.id}

@api_router.post("/enroll/{course_id}")
async def enroll_course(course_id: str, current_user: User = Depends(get_current_user)):
    # Check if course exists
    course = await db.courses.find_one({"id": course_id})
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    # Check if already enrolled
    existing_enrollment = await db.enrollments.find_one({
        "user_id": current_user.id,
        "course_id": course_id
    })
    if existing_enrollment:
        raise HTTPException(status_code=400, detail="Already enrolled in this course")
    
    # Create enrollment
    enrollment = Enrollment(user_id=current_user.id, course_id=course_id)
    await db.enrollments.insert_one(enrollment.dict())
    
    # Update course enrollment count
    await db.courses.update_one(
        {"id": course_id},
        {"$inc": {"total_enrollments": 1}}
    )
    
    return {"message": "Enrolled successfully"}

@api_router.get("/my-courses")
async def get_my_courses(current_user: User = Depends(get_current_user)):
    try:
        enrollments = await db.enrollments.find({"user_id": current_user.id}).to_list(100)
        course_ids = [e["course_id"] for e in enrollments]
        courses = await db.courses.find({"id": {"$in": course_ids}}).to_list(100)
        
        # Combine course data with enrollment progress
        result = []
        for course in courses:
            enrollment = next(e for e in enrollments if e["course_id"] == course["id"])
            result.append({
                **convert_objectid(course),
                "progress": enrollment["progress"],
                "completed": enrollment["completed"],
                "enrolled_at": enrollment["enrolled_at"]
            })
        
        return result
    except Exception as e:
        logger.error(f"Error fetching user courses: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching user courses")

@api_router.post("/chat")
async def chat_with_bot(request: ChatRequest):
    try:
        # Get relevant context using RAG
        context = get_rag_context(request.message)
        
        # Create prompt for Groq
        prompt = f"""You are a helpful AI assistant for an AI & Machine Learning course. Use the following context to answer the user's question accurately and helpfully.

Context:
{context}

User Question: {request.message}

Please provide a helpful, accurate response based on the course content. If the question is not related to the course content, politely redirect the conversation back to the course topics."""

        # Call Groq API
        response = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a helpful AI assistant for an AI & Machine Learning course."},
                {"role": "user", "content": prompt}
            ],
            model="llama3-8b-8192",
            max_tokens=1000,
            temperature=0.7
        )
        
        bot_response = response.choices[0].message.content
        
        # Save chat message
        chat_message = ChatMessage(
            session_id=request.session_id,
            message=request.message,
            response=bot_response
        )
        await db.chat_messages.insert_one(chat_message.dict())
        
        return {"response": bot_response}
        
    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        raise HTTPException(status_code=500, detail="Chat service unavailable")

@api_router.get("/chat/history/{session_id}")
async def get_chat_history(session_id: str):
    try:
        messages = await db.chat_messages.find(
            {"session_id": session_id}
        ).sort("timestamp", 1).to_list(100)
        return convert_objectid(messages)
    except Exception as e:
        logger.error(f"Error fetching chat history: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching chat history")

@api_router.post("/reviews")
async def create_review(review_data: Dict[str, Any], current_user: User = Depends(get_current_user)):
    review = Review(
        course_id=review_data["course_id"],
        user_id=current_user.id,
        user_name=current_user.full_name,
        rating=review_data["rating"],
        comment=review_data["comment"]
    )
    await db.reviews.insert_one(review.dict())
    
    # Update course rating
    reviews = await db.reviews.find({"course_id": review_data["course_id"]}).to_list(1000)
    avg_rating = sum(r["rating"] for r in reviews) / len(reviews)
    await db.courses.update_one(
        {"id": review_data["course_id"]},
        {"$set": {"rating": round(avg_rating, 1)}}
    )
    
    return {"message": "Review added successfully"}

@api_router.get("/reviews/{course_id}")
async def get_course_reviews(course_id: str):
    try:
        reviews = await db.reviews.find({"course_id": course_id}).sort("created_at", -1).to_list(100)
        return convert_objectid(reviews)
    except Exception as e:
        logger.error(f"Error fetching reviews: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching reviews")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup event
    # Create sample course if none exists
    course_count = await db.courses.count_documents({})
    if course_count == 0:
        sample_course = Course(
            title="AI & Machine Learning Fundamentals",
            description="Master the fundamentals of artificial intelligence and machine learning with hands-on projects and real-world applications.",
            syllabus=COURSE_CONTENT["ai_ml_fundamentals"]["syllabus"],
            price=299.99,
            duration_weeks=8,
            difficulty_level="Beginner to Intermediate",
            instructor="Dr. Sarah Johnson",
            enrollment_deadline=datetime.utcnow() + timedelta(days=30),
            rating=4.8,
            total_enrollments=1247
        )
        await db.courses.insert_one(sample_course.dict())
        
        # Add sample reviews
        sample_reviews = [
            Review(
                course_id=sample_course.id,
                user_id="sample-user-1",
                user_name="Alex Chen",
                rating=5,
                comment="Excellent course! The hands-on projects really helped me understand ML concepts."
            ),
            Review(
                course_id=sample_course.id,
                user_id="sample-user-2", 
                user_name="Maria Rodriguez",
                rating=5,
                comment="Dr. Johnson explains complex topics in a very clear and engaging way."
            ),
            Review(
                course_id=sample_course.id,
                user_id="sample-user-3",
                user_name="David Kim",
                rating=4,
                comment="Great content and structure. Would recommend to anyone starting in AI/ML."
            )
        ]
        for review in sample_reviews:
            await db.reviews.insert_one(review.dict())
    
    yield  # This is where the application runs
    
    # Shutdown event
    # Add any cleanup code here if needed
    # client.close()  # Uncomment if you need to close the MongoDB client

# Create FastAPI app with lifespan
app = FastAPI(lifespan=lifespan)

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Shutdown is now handled in the lifespan context manager

# Run the server with uvicorn when this script is executed directly
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
