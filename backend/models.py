from sqlalchemy import Column, Integer, String, DECIMAL, Text, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import TIMESTAMP, JSONB
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class Tag(Base):
    __tablename__ = "tags"
    
    tag_id = Column(String(20), primary_key=True)
    tag_name = Column(String(100))
    unit_type = Column(String(50))
    data_type = Column(String(20))
    normal_min = Column(DECIMAL)
    normal_max = Column(DECIMAL)
    scan_rate_sec = Column(Integer)
    description = Column(Text)
    
    readings = relationship("TagReading", back_populates="tag")

class TagReading(Base):
    __tablename__ = "tag_readings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tag_id = Column(String(20), ForeignKey("tags.tag_id"))
    timestamp = Column(DateTime(timezone=True), nullable=False)
    value = Column(DECIMAL)
    quality_code = Column(String(10))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    
    tag = relationship("Tag", back_populates="readings")

class Anomaly(Base):
    __tablename__ = "anomalies"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tag_id = Column(String(20), ForeignKey("tags.tag_id"))
    anomaly_type = Column(String(50))
    confidence = Column(DECIMAL)
    evidence = Column(JSONB)
    detected_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    hitl_status = Column(String(20), default="pending")
    hypothesis = Column(Text)
    recommended_action = Column(Text)
    
    tag = relationship("Tag")

class AgentTrace(Base):
    __tablename__ = "agent_trace"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_name = Column(String(50))
    input = Column(JSONB)
    output = Column(JSONB)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
