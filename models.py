from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, Text
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
from sqlalchemy import JSON


Base = declarative_base()

class ExamLevel(Base):
    __tablename__ = 'exam_levels'
    id = Column(Integer, primary_key=True)
    name = Column(String(20), unique=True, nullable=False)  # "HSK 1", "HSK 2", ...

class Section(Base):
    __tablename__ = 'sections'
    id = Column(Integer, primary_key=True)
    name = Column(String(20), unique=True, nullable=False)  # "аудирование", "чтение", "письмо"

class Task(Base):
    __tablename__ = 'tasks'
    id = Column(Integer, primary_key=True)
    level_id = Column(Integer, ForeignKey('exam_levels.id'), nullable=False)
    section_id = Column(Integer, ForeignKey('sections.id'), nullable=False)
    task_number = Column(Integer, nullable=False)
    photo_file_id = Column(String(255), nullable=False)
    audio_file_id = Column(String(255), nullable=True)  # only for listening
    comment_text = Column(Text, nullable=False)
    correct_answer = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


    level = relationship("ExamLevel")
    section = relationship("Section")

# Optional: for analytics
class UserSession(Base):
    __tablename__ = 'user_sessions'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    task_id = Column(Integer, ForeignKey('tasks.id'), nullable=False)
    user_answer = Column(Text, nullable=True)
    is_correct = Column(Boolean, nullable=True)  # null for writing
    submitted_at = Column(DateTime, default=datetime.utcnow)

    task = relationship("Task")