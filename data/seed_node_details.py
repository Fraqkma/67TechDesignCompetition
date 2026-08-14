"""Fill teaching detail content (techniques / learningOutcomes / realWorld) for
every node in the connected PostgreSQL database.

The graph structure (careers, nodes, prerequisites) is the single source of
truth and lives in the DB.  These three columns are display-only teaching
content consumed by the roadmap detail panel and the AI assistant; they used
to be empty JSON arrays.  This script backfills them once (idempotent: it only
updates rows whose columns are still empty).

Run from the project root:
    python data/seed_node_details.py
"""

from __future__ import annotations

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import get_db  # noqa: E402

# node id -> teaching content.  Keep 3-4 bullets per field so the roadmap
# detail panel and the AI assistant have useful material to work with.
NODE_DETAILS: dict[int, dict[str, list[str]]] = {
    1: {  # Git & Version Control Workflow
        "techniques": [
            "ใช้ Git Flow / Feature Branch เพื่อแยกงานแต่ละฟีเจอร์",
            "เขียน Commit Message แบบ Conventional Commits ให้ประวัติการแก้ไขอ่านง่าย",
            "แก้ Conflict อย่างมีหลักการด้วย Rebase หรือ Merge",
            "ใช้ git bisect / git log -p ไล่หาที่มาของ Bug",
        ],
        "learningOutcomes": [
            "สร้าง Repository และจัดการ Branch ได้อย่างคล่องตัว",
            "ส่ง Pull Request และรีวิวโค้ดร่วมกับทีมได้",
            "กู้คืนโค้ดย้อนกลับเมื่อมีปัญหา",
        ],
        "realWorld": [
            "ทำงานร่วมกันเป็นทีมบน GitHub/GitLab โดยไม่ทับโค้ดกัน",
            "ทำ Release/Deploy ตาม Tag และ Version ที่กำหนด",
            "ใช้ Git เก็บโค้ดในงาน Open Source และงานจริง",
        ],
    },
    2: {  # Linux Administration & Shell Scripting
        "techniques": [
            "จัดการสิทธิ์ไฟล์ด้วย chmod/chown และเข้าใจ umask",
            "เขียน Bash Script พร้อม Error Handling (set -e, trap)",
            "ใช้ systemd จัดการ Service และตรวจสอบ Log ด้วย journalctl",
            "ใช้ grep/awk/sed วิเคราะห์ไฟล์ Log",
        ],
        "learningOutcomes": [
            "บริหารจัดการผู้ใช้ สิทธิ์ และ Process บน Linux ได้",
            "เขียน Script อัตโนมัติสำหรับงานประจำได้",
            "ติดตั้งและดูแล Package ผ่าน APT/DNF ได้",
        ],
        "realWorld": [
            "ตั้งค่าและดูแล Server บน Cloud / On-premise",
            "ทำ Cron Job และงาน Automation สำรองข้อมูล",
            "แก้ปัญหา Server ไม่ทำงานด้วยการอ่าน Log",
        ],
    },
    3: {  # Advanced Python Programming
        "techniques": [
            "ใช้ List/Dict Comprehension และ Generator ให้โค้ดสั้นและเร็ว",
            "ออกแบบด้วย OOP: Encapsulation, Inheritance, Composition",
            "ใช้ Decorators และ Context Manager กับงานซ้ำซ้อน",
            "จัดการ Virtual Environment และ Dependency ด้วย venv/uv",
        ],
        "learningOutcomes": [
            "เขียนโค้ด Python ที่อ่านง่ายและมีประสิทธิภาพ",
            "ออกแบบ Class และ Module ที่นำกลับมาใช้ใหม่ได้",
            "จัดการข้อยกเว้นและทรัพยากรอย่างปลอดภัย",
        ],
        "realWorld": [
            "เขียนเครื่องมือวิเคราะห์ข้อมูลและ Automation",
            "พัฒนา API ด้วย FastAPI และโปรเจกต์ Backend",
            "สร้างเทมเพลตโค้ดที่ทีมใช้ร่วมกัน",
        ],
    },
    4: {  # Relational Database & Advanced SQL
        "techniques": [
            "ออกแบบ ER Diagram และทำ Normalization (1NF-3NF)",
            "ใช้ EXPLAIN ANALYZE เพื่อปรับปรุง Query",
            "เขียน Window Functions (ROW_NUMBER, LAG) สำหรับรายงาน",
            "ใช้ Index, Transaction และ Lock อย่างถูกต้อง",
        ],
        "learningOutcomes": [
            "ออกแบบ Schema ฐานข้อมูลที่เป็นระบบ",
            "เขียน Query ที่ซับซ้อนได้อย่างมีประสิทธิภาพ",
            "รักษาความถูกต้องของข้อมูลด้วยหลักการ ACID",
        ],
        "realWorld": [
            "ออกแบบฐานข้อมูลระบบ E-commerce / ERP",
            "ทำรายงานยอดขายด้วย Window Functions",
            "ปรับปรุง Query ที่ช้าในระบบ Production",
        ],
    },
    5: {  # NoSQL & In-Memory Caching
        "techniques": [
            "ออกแบบ Document Schema ใน MongoDB ให้เหมาะกับรูปแบบการอ่านข้อมูล",
            "ใช้ Redis แบบ Cache-Aside พร้อม TTL ที่เหมาะสม",
            "จัดการ Session และ Rate Limiting ด้วย Redis",
            "เลือกใช้ NoSQL ให้ตรงกับงาน (เอกสาร / คีย์-ค่า)",
        ],
        "learningOutcomes": [
            "ออกแบบและค้นข้อมูล MongoDB ได้",
            "นำ Redis ไปทำ Cache และ Queue ได้",
            "อธิบายข้อดีข้อเสียเทียบกับฐานข้อมูล SQL",
        ],
        "realWorld": [
            "ลด Latency ของ API ด้วย Redis Cache",
            "เก็บ Session ผู้ใช้ในระบบ Login",
            "ทำ Rate Limiting ป้องกัน API ถูกโจมตี",
        ],
    },
    6: {  # Computer Networks & TCP/IP Protocol Stack
        "techniques": [
            "วิเคราะห์การทำงานของ OSI/TCP/IP ทีละชั้น",
            "ใช้ Wireshark/tcpdump จับและวิเคราะห์ Packet",
            "คำนวณ Subnet และจัดสรร IP Address",
            "ตรวจสอบปัญหาการเชื่อมต่อด้วย ping/traceroute/DNS",
        ],
        "learningOutcomes": [
            "อธิบายการสื่อสารผ่าน TCP/IP ได้",
            "ตั้งค่าและแก้ปัญหาเครือข่ายเบื้องต้นได้",
            "วิเคราะห์ HTTP/HTTPS และ WebSocket ได้",
        ],
        "realWorld": [
            "แก้ปัญหาเว็บโหลดช้า / ต่อไม่ได้",
            "ออกแบบเครือข่ายองค์กรและ Cloud VPC",
            "วิเคราะห์การโจมตีผ่าน Network Traffic",
        ],
    },
    7: {  # Operating Systems Internals
        "techniques": [
            "วาด Diagram ของ Process/Thread เพื่อเข้าใจ Scheduling",
            "วิเคราะห์ Deadlock และหา Safe Sequence",
            "ทดลองจัดการ Concurrency ด้วย Lock/Semaphore",
            "อ่านกลไก Paging และ Virtual Memory",
        ],
        "learningOutcomes": [
            "อธิบายการทำงานของ Scheduler และ Memory Manager",
            "เขียนโปรแกรม Concurrent ที่ปลอดภัย",
            "วิเคราะห์สาเหตุระบบค้าง / ช้า",
        ],
        "realWorld": [
            "ปรับแต่งประสิทธิภาพ Server (CPU/Memory)",
            "ออกแบบระบบ Embedded ที่ใช้ทรัพยากรจำกัด",
            "วิเคราะห์ปัญหา Thread/Process ในระบบ Production",
        ],
    },
    8: {  # Linear Algebra & Calculus for Engineers
        "techniques": [
            "ใช้เมทริกซ์และ Eigenvalue แก้ปัญหาการแปลงข้อมูล",
            "ต่อยอด Gradient Descent จาก Partial Derivative",
            "ตรวจมิติของเมทริกซ์ทุกครั้งก่อนคำนวณ",
            "ใช้ NumPy/SymPy ตรวจคำตอบ",
        ],
        "learningOutcomes": [
            "คำนวณเมทริกซ์ เวกเตอร์ และ Eigenvalue ได้",
            "เข้าใจหลักการ Differentiation ที่ใช้ใน ML",
            "อธิบายการทำงานของ Gradient Descent ได้",
        ],
        "realWorld": [
            "เข้าใจหลักการทำงานของ PCA และ ML Model",
            "วิเคราะห์ภาพ 3D และ Computer Graphics",
            "คำนวณและจำลองระบบทางวิศวกรรม",
        ],
    },
    9: {  # Applied Statistics & Probability
        "techniques": [
            "เลือกสถิติอธิบายข้อมูลให้ตรงกับชนิดตัวแปร",
            "ตั้งสมมติฐาน (H0/H1) ก่อนทำ Hypothesis Test",
            "ตีความ p-value และ Confidence Interval อย่างถูกต้อง",
            "ออกแบบ A/B Test พร้อมกำหนดขนาดตัวอย่าง",
        ],
        "learningOutcomes": [
            "วิเคราะห์ข้อมูลเชิงสถิติและสรุปผลได้",
            "ทำ Hypothesis Testing และ A/B Test ได้",
            "อธิบายความไม่แน่นอนของข้อมูลด้วยความน่าจะเป็น",
        ],
        "realWorld": [
            "ประเมินผล Feature ใหม่ด้วย A/B Test",
            "วิเคราะห์ความเสี่ยงและคาดการณ์ยอดขาย",
            "ใช้สถิติตรวจสอบคุณภาพข้อมูลใน Data Pipeline",
        ],
    },
    10: {  # Modern Web Fundamentals (HTML5/CSS3/JS)
        "techniques": [
            "เขียน HTML แบบ Semantic เพื่อ SEO และ Accessibility",
            "ใช้ Flexbox/Grid จัด Layout ให้ Responsive",
            "จัดการงาน Asynchronous ด้วย Promise/async-await",
            "ใช้ DevTools ตรวจสอบและ Debug",
        ],
        "learningOutcomes": [
            "สร้างหน้าเว็บ Responsive ได้",
            "เขียน JavaScript ที่จัดการเหตุการณ์และข้อมูลได้",
            "เชื่อมต่อ API จากหน้าเว็บได้",
        ],
        "realWorld": [
            "สร้างหน้า Landing Page / โปรเจกต์ Frontend",
            "ทำฟอร์มสมัครสมาชิกพร้อม Validation",
            "แสดงข้อมูลแบบ Real-time จาก API",
        ],
    },
    11: {  # Modern Frontend Frameworks (React & Next.js)
        "techniques": [
            "แยก Component เป็นหน่วยเล็กที่นำกลับมาใช้ใหม่ได้",
            "จัดการ State ด้วย Hooks และ State Library",
            "ใช้ Next.js SSR/SSG เพื่อ SEO และความเร็ว",
            "เชื่อมต่อ API อย่างมีระบบ (React Query/SWR)",
        ],
        "learningOutcomes": [
            "พัฒนา SPA/SSR ด้วย React และ Next.js",
            "จัดการ State และ Lifecycle ได้อย่างถูกต้อง",
            "ทำ Performance Optimization (Code Splitting, Memoization)",
        ],
        "realWorld": [
            "สร้างเว็บแอปที่รองรับผู้ใช้จำนวนมาก",
            "พัฒนา Dashboard / Admin Panel",
            "ทำ E-commerce และเว็บเนื้อหาที่ติด SEO",
        ],
    },
    12: {  # RESTful, GraphQL & gRPC API Design
        "techniques": [
            "ออกแบบ RESTful API แบบ Resource-based และ Versioned",
            "เขียน GraphQL Schema พร้อม Resolver ที่มีประสิทธิภาพ",
            "ใช้ gRPC + Protocol Buffers สำหรับบริการภายใน",
            "ออกแบบ Authentication ด้วย JWT และ OAuth2",
        ],
        "learningOutcomes": [
            "ออกแบบและเขียนเอกสาร API อย่างเป็นมาตรฐาน",
            "สร้าง GraphQL / gRPC API ได้",
            "รักษาความปลอดภัยของ API ได้",
        ],
        "realWorld": [
            "ออกแบบ API ให้ทีม Mobile/Web ใช้งานร่วมกัน",
            "สร้าง Microservices ที่สื่อสารด้วย gRPC",
            "ทำ API Gateway สำหรับบริการต่าง ๆ",
        ],
    },
    13: {  # Data Structures & Algorithms
        "techniques": [
            "วิเคราะห์ Big-O ก่อนเลือก Data Structure",
            "ฝึกแก้โจทย์แบบ Pattern (Two Pointers, Sliding Window)",
            "วาด Diagram ของ Tree/Graph ก่อนเขียนโค้ด",
            "เขียน Pseudocode แล้วค่อยแปลงเป็นโค้ด",
        ],
        "learningOutcomes": [
            "เลือก Data Structure ให้เหมาะสมกับปัญหา",
            "เขียน Algorithm แก้ปัญหาอย่างมีประสิทธิภาพ",
            "วิเคราะห์ความซับซ้อนของโค้ดได้",
        ],
        "realWorld": [
            "ผ่านการสัมภาษณ์งานสาย Software",
            "ออกแบบระบบค้นหาและจัดเรียงข้อมูล",
            "แก้ปัญหา Performance ในระบบจริง",
        ],
    },
    14: {  # Software Testing & Quality Assurance
        "techniques": [
            "เขียน Unit Test ให้ครอบคลุม Edge Case",
            "ทำ TDD: แดง-เขียว-รีแฟกเตอร์",
            "Mock Dependency เพื่อแยกการทดสอบ",
            "ใช้ CI รัน Test อัตโนมัติทุก Commit",
        ],
        "learningOutcomes": [
            "เขียน Unit / Integration / E2E Test ได้",
            "นำ TDD ไปใช้ในงานจริง",
            "วัด Coverage และปรับปรุงคุณภาพโค้ด",
        ],
        "realWorld": [
            "รับประกันคุณภาพก่อน Release",
            "ลด Bug ใน Production ด้วยระบบ Test",
            "เขียน E2E Test ด้วย Cypress/Playwright",
        ],
    },
    15: {  # System Design & High Scalability Architecture
        "techniques": [
            "เริ่มจาก Requirement แล้ววาด High-level Diagram",
            "แบ่งระบบเป็น Microservices ตาม Bounded Context",
            "ใช้ Load Balancer + Message Queue รองรับการขยายตัว",
            "วิเคราะห์ CAP และเลือก Consistency ที่เหมาะสม",
        ],
        "learningOutcomes": [
            "ออกแบบสถาปัตยกรรมระบบขนาดใหญ่",
            "อธิบายการทำ Sharding/Replication ได้",
            "ประเมินจุดคอขวดและวางแผนขยายระบบ",
        ],
        "realWorld": [
            "ออกแบบระบบที่รองรับผู้ใช้หลายล้านคน",
            "เตรียมตัวสัมภาษณ์ System Design",
            "วางแผน Scaling ให้ระบบ E-commerce",
        ],
    },
    16: {  # Data Warehousing & Data Modeling
        "techniques": [
            "ออกแบบ Star/Snowflake Schema ตามแนวคิด Kimball",
            "ทำ Dimensional Modeling: Fact + Dimension",
            "จัดการ SCD (Slowly Changing Dimension)",
            "วางแผน Data Lakehouse และ Metadata",
        ],
        "learningOutcomes": [
            "ออกแบบ Data Warehouse ที่ตอบโจทย์รายงาน",
            "สร้าง Data Model ที่ยืดหยุ่นต่อการขยาย",
            "จัดการคุณภาพและ Metadata ของข้อมูล",
        ],
        "realWorld": [
            "สร้างฐานข้อมูลสำหรับ BI Dashboard",
            "รวบรวมข้อมูลหลายระบบเข้าสู่ Data Warehouse",
            "วาง Data Platform ให้องค์กร",
        ],
    },
    17: {  # Data Ingestion & Orchestration (Airflow)
        "techniques": [
            "ออกแบบ DAG ให้ Task พึ่งพากันน้อยที่สุด",
            "จัดการ Retry, Backfill และ Schedule อย่างถูกต้อง",
            "ทำ Data Validation ในทุกขั้นตอนของ Pipeline",
            "ใช้ Airflow Variables/Connections เก็บค่า Config",
        ],
        "learningOutcomes": [
            "สร้าง ETL/ELT Pipeline ด้วย Airflow",
            "ทำ Data Cleaning และ Transformation",
            "ตรวจสอบและกู้คืน Pipeline ที่ล้มเหลว",
        ],
        "realWorld": [
            "ย้ายข้อมูลจากหลายแหล่งเข้าสู่ Data Warehouse ทุกวัน",
            "ทำระบบแจ้งเตือนเมื่อ Pipeline ผิดพลาด",
            "สร้าง Data Platform ให้ทีม Data",
        ],
    },
    18: {  # Distributed Data Processing (Apache Spark)
        "techniques": [
            "ใช้ DataFrame API แทน RDD เพื่อให้อ่านง่ายและเร็ว",
            "จัด Partition ให้สมดุลเพื่อประสิทธิภาพ",
            "หลีกเลี่ยง Shuffle ที่ไม่จำเป็น",
            "จัดการ OOM ด้วยการปรับ Memory และ Cache",
        ],
        "learningOutcomes": [
            "ประมวลผลข้อมูลขนาดใหญ่ด้วย PySpark",
            "ปรับแต่งประสิทธิภาพ Spark Job ได้",
            "จัดการปัญหา Out-of-Memory ในคลัสเตอร์",
        ],
        "realWorld": [
            "ประมวลผลข้อมูลหลาย TB ต่อวัน",
            "สร้าง Feature Store สำหรับ Machine Learning",
            "วิเคราะห์ Log จำนวนมหาศาล",
        ],
    },
    19: {  # Real-time Event Streaming (Apache Kafka)
        "techniques": [
            "ออกแบบ Topic/Partition ให้รองรับ Consumer ที่หลากหลาย",
            "จัดการ Consumer Group และ Offset อย่างถูกต้อง",
            "ใช้ Idempotent Producer เพื่อไม่ให้ข้อมูลซ้ำ",
            "วางแผน Retention และ Replication",
        ],
        "learningOutcomes": [
            "สร้าง Producer/Consumer ด้วย Kafka",
            "ออกแบบ Event-driven Architecture",
            "จัดการ Stream Processing (Kafka Streams/KSQL)",
        ],
        "realWorld": [
            "ทำระบบ Tracking พฤติกรรมผู้ใช้แบบ Real-time",
            "เชื่อมต่อ Microservices ด้วย Event",
            "สร้างระบบแจ้งเตือนและ Recommendation",
        ],
    },
    20: {  # Cloud Data Warehouses (Snowflake / BigQuery)
        "techniques": [
            "ออกแบบ Partitioning/Clustering ให้ Query เร็ว",
            "ใช้ SQL คำนวณข้อมูลระดับ Terabyte",
            "จัดการ Cost ด้วยการแยก Compute และ Storage",
            "ใช้ Time Travel / Snapshot เพื่อกู้ข้อมูล",
        ],
        "learningOutcomes": [
            "ใช้งาน Snowflake/BigQuery คำนวณข้อมูลขนาดใหญ่",
            "ออกแบบตารางให้ประหยัดค่าใช้จ่าย",
            "ทำ Data Sharing ระหว่างทีม",
        ],
        "realWorld": [
            "สร้าง Data Mart สำหรับ BI ในองค์กร",
            "วิเคราะห์ข้อมูลจากหลายแหล่งแบบรวมศูนย์",
            "ทำ Analytics แบบ Real-time",
        ],
    },
    21: {  # Data Wrangling & Analysis (Pandas & Polars)
        "techniques": [
            "ใช้ Vectorized Operation แทน Loop เพื่อความเร็ว",
            "ทำ Data Cleaning: จัดการ Missing / Outlier",
            "ใช้ GroupBy + Aggregate วิเคราะห์ข้อมูล",
            "สร้าง Visualization เพื่อสำรวจข้อมูล (EDA)",
        ],
        "learningOutcomes": [
            "จัดการและเตรียมข้อมูลด้วย Pandas/Polars",
            "ทำ EDA และสรุป Insights จากข้อมูล",
            "สร้างกราฟสื่อสารผลการวิเคราะห์",
        ],
        "realWorld": [
            "เตรียมข้อมูลก่อนเข้า Machine Learning Model",
            "วิเคราะห์ข้อมูลธุรกิจเพื่อการตัดสินใจ",
            "สร้างรายงานข้อมูลอัตโนมัติ",
        ],
    },
    22: {  # Applied Machine Learning (Scikit-Learn)
        "techniques": [
            "ทำ Feature Engineering และ Scaling อย่างถูกต้อง",
            "ใช้ Cross-Validation ประเมินโมเดล",
            "จัดการ Overfitting ด้วย Regularization",
            "ใช้ Pipeline ป้องกัน Data Leakage",
        ],
        "learningOutcomes": [
            "สร้างโมเดล Regression / Classification / Clustering",
            "ประเมินและเปรียบเทียบโมเดลได้",
            "ปรับ Hyperparameter อย่างเป็นระบบ",
        ],
        "realWorld": [
            "พยากรณ์ยอดขาย / ความต้องการสินค้า",
            "ทำระบบแนะนำและจัดกลุ่มลูกค้า",
            "สร้างโมเดลจำแนกข้อมูลอัตโนมัติ",
        ],
    },
    23: {  # Deep Learning & Neural Networks (PyTorch)
        "techniques": [
            "เริ่มจาก Tensor และ Autograd เพื่อเข้าใจหลักการ",
            "ออกแบบ Architecture: CNN / RNN / Transformer",
            "จัดการ Training Loop: Optimizer, Loss, LR Scheduling",
            "ใช้ GPU และ Mixed Precision เพื่อเร่ง Training",
        ],
        "learningOutcomes": [
            "สร้างและเทรนโมเดล Deep Learning ด้วย PyTorch",
            "อธิบายการทำงานของ CNN/RNN/Transformer",
            "ปรับแต่ง LLM/NLP เบื้องต้นได้",
        ],
        "realWorld": [
            "สร้างระบบตรวจจับวัตถุจากภาพ",
            "ทำ Text Classification / Chatbot",
            "นำ LLM มาประยุกต์กับงานองค์กร",
        ],
    },
    24: {  # MLOps & Model Lifecycle Management
        "techniques": [
            "บันทึก Experiment ด้วย MLflow (Params/Metrics/Artifacts)",
            "ทำ Model Registry และ Versioning",
            "ตรวจสอบ Data/Model Drift ใน Production",
            "ออกแบบ Feature Store ให้ทีมใช้ร่วมกัน",
        ],
        "learningOutcomes": [
            "Deploy โมเดลสู่ Production ได้",
            "จัดการวงจรชีวิตโมเดลอย่างเป็นระบบ",
            "ติดตามประสิทธิภาพโมเดลหลัง Deploy",
        ],
        "realWorld": [
            "นำ ML Model ไปใช้งานจริงในธุรกิจ",
            "ทำระบบแจ้งเตือนเมื่อโมเดลเสื่อมคุณภาพ",
            "สร้าง Platform ML ที่ทีม Data ใช้ร่วมกัน",
        ],
    },
    25: {  # Containerization with Docker
        "techniques": [
            "เขียน Dockerfile แบบ Multi-stage เพื่อลดขนาด Image",
            "จัดการ Container Isolation และ Network",
            "ใช้ Docker Compose จัดการหลาย Service",
            "ทำ Healthcheck และ Logging",
        ],
        "learningOutcomes": [
            "สร้างและรัน Container ด้วย Docker",
            "เขียน Dockerfile ที่ปลอดภัยและเล็ก",
            "จัดการ Multi-container ด้วย Compose",
        ],
        "realWorld": [
            "ทำให้แอป Deploy ได้ทุกที่เหมือนกัน",
            "รัน Local Environment เดียวกันทั้งทีม",
            "เตรียมพื้นฐานสำหรับ Kubernetes",
        ],
    },
    26: {  # Infrastructure as Code (Terraform)
        "techniques": [
            "เขียน HCL ประกาศ Resources แบบ Declarative",
            "จัดการ State อย่างปลอดภัย (Remote State, Lock)",
            "ใช้ Modules เพื่อนำโครงสร้างพื้นฐานกลับมาใช้ใหม่",
            "วางแผน Apply/Destroy อย่างรอบคอบ",
        ],
        "learningOutcomes": [
            "สร้างและจัดการ Cloud Resources ด้วย Terraform",
            "เข้าใจ State Management และ Modules",
            "ทำ Infrastructure Versioning ได้",
        ],
        "realWorld": [
            "สร้าง VPC/EC2/S3 อัตโนมัติตามมาตรฐานทีม",
            "ทำ Disaster Recovery ด้วยการสร้างใหม่จาก Code",
            "จัดการโครงสร้างพื้นฐานหลาย Environment",
        ],
    },
    27: {  # CI/CD Automation Pipelines
        "techniques": [
            "แบ่ง Pipeline: Build → Test → Security Scan → Deploy",
            "ใช้ Caching และ Parallel Jobs ให้เร็วขึ้น",
            "จัดการ Secret อย่างปลอดภัย",
            "ทำ Automatic Rollback เมื่อ Deploy ล้มเหลว",
        ],
        "learningOutcomes": [
            "สร้าง CI/CD Pipeline ด้วย GitHub Actions/GitLab CI",
            "ทำ Automated Testing ในทุก Commit",
            "Deploy อัตโนมัติอย่างปลอดภัย",
        ],
        "realWorld": [
            "ส่งโค้ดขึ้น Production โดยอัตโนมัติ",
            "ลดเวลาและความผิดพลาดในการ Release",
            "รับประกันคุณภาพโค้ดด้วย Test ใน Pipeline",
        ],
    },
    28: {  # Container Orchestration with Kubernetes
        "techniques": [
            "จัดการ Pod/Deployment/Service ผ่าน YAML Manifest",
            "ใช้ Helm Chart จัดการ Application ที่ซับซ้อน",
            "ตั้งค่า HPA สำหรับ Auto-scaling",
            "จัดการ Persistent Volume และ Config",
        ],
        "learningOutcomes": [
            "Deploy และจัดการแอปบน Kubernetes",
            "ตั้งค่า Scaling และ Self-healing",
            "ใช้ Ingress และ ConfigMap อย่างถูกต้อง",
        ],
        "realWorld": [
            "รันบริการ Production บนคลัสเตอร์",
            "รองรับ Traffic ที่เพิ่มขึ้นแบบอัตโนมัติ",
            "จัดการหลาย Environment (dev/staging/prod)",
        ],
    },
    29: {  # Observability & Monitoring (Prometheus & Grafana)
        "techniques": [
            "เก็บ Metrics ด้วย Prometheus (PromQL)",
            "รวบรวม Log ด้วย Loki/ELK",
            "ทำ Distributed Tracing เพื่อวิเคราะห์ Latency",
            "ออกแบบ Dashboard และ Alert ที่อ่านง่าย",
        ],
        "learningOutcomes": [
            "ติดตั้งและตั้งค่า Prometheus/Grafana",
            "เขียน PromQL เพื่อสอบถาม Metrics",
            "ตั้งค่า Alert เมื่อระบบมีปัญหา",
        ],
        "realWorld": [
            "ติดตามสุขภาพระบบ Production แบบ Real-time",
            "วิเคราะห์สาเหตุเมื่อเกิด Outage",
            "รายงาน SLO/SLA ให้ทีมบริหาร",
        ],
    },
    30: {  # Cloud Architecture (AWS / GCP)
        "techniques": [
            "ออกแบบ VPC/Subnet/Networking ให้ปลอดภัย",
            "ใช้ Compute ที่เหมาะกับงาน (EC2/Lambda)",
            "ออกแบบ Storage และ Backup (S3/Blob Storage)",
            "จัดการสิทธิ์ด้วย IAM ตามหลัก Least Privilege",
        ],
        "learningOutcomes": [
            "ออกแบบสถาปัตยกรรมบน AWS/GCP",
            "สร้างระบบ Serverless ได้",
            "บริหารต้นทุนและความปลอดภัยบน Cloud",
        ],
        "realWorld": [
            "ย้ายระบบองค์กรขึ้น Cloud",
            "สร้างแอปที่ Scale อัตโนมัติตาม Traffic",
            "ทำระบบสำรองข้อมูล Disaster Recovery",
        ],
    },
    31: {  # Cybersecurity Fundamentals & Threat Modeling
        "techniques": [
            "ใช้ CIA Triad และ Defense in Depth เป็นกรอบคิด",
            "ทำ Threat Modeling ด้วย STRIDE",
            "ประเมินความเสี่ยงตามมาตรฐาน NIST/ISO27001",
            "เขียน Security Policy และ Incident Plan",
        ],
        "learningOutcomes": [
            "วิเคราะห์ความเสี่ยงด้านความปลอดภัย",
            "ทำ Threat Modeling ของระบบได้",
            "อธิบายมาตรฐานความปลอดภัยองค์กร",
        ],
        "realWorld": [
            "ประเมินความปลอดภัยระบบก่อนเปิดตัว",
            "ออกแบบระบบตามแนวทาง Zero Trust",
            "จัดทำเอกสารการรับรองมาตรฐาน",
        ],
    },
    32: {  # Web Application Security & OWASP Top 10
        "techniques": [
            "ป้องกัน SQL Injection ด้วย Parameterized Query",
            "หลีกเลี่ยง XSS ด้วยการ Escape Output",
            "ป้องกัน CSRF ด้วย Token และ SameSite Cookie",
            "ทดสอบช่องโหว่ด้วย Burp Suite / OWASP ZAP",
        ],
        "learningOutcomes": [
            "ตรวจจับและแก้ไขช่องโหว่ OWASP Top 10",
            "เขียนโค้ดเว็บที่ปลอดภัย",
            "ทำ Security Testing เบื้องต้น",
        ],
        "realWorld": [
            "ตรวจสอบความปลอดภัยเว็บแอปก่อน Release",
            "แก้ช่องโหว่ที่พบจากการ Pentest",
            "ปกป้องข้อมูลผู้ใช้จากการโจมตี",
        ],
    },
    33: {  # Applied Cryptography & PKI
        "techniques": [
            "เลือกใช้ Symmetric/Asymmetric ให้เหมาะกับงาน",
            "ใช้ Hash Function และ Salt เก็บรหัสผ่าน",
            "ออกแบบ Digital Signature และ TLS",
            "จัดการ Certificate ผ่าน PKI",
        ],
        "learningOutcomes": [
            "เข้ารหัสและถอดรหัสข้อมูลได้อย่างถูกต้อง",
            "ตั้งค่า TLS/SSL Certificate ได้",
            "อธิบายการทำงานของ PKI",
        ],
        "realWorld": [
            "ทำให้เว็บปลอดภัยด้วย HTTPS",
            "ออกแบบระบบ Authentication ที่ปลอดภัย",
            "จัดการ Key และ Certificate ขององค์กร",
        ],
    },
    34: {  # SOC, SIEM & Incident Response
        "techniques": [
            "รวบรวม Log เข้า SIEM (Splunk/Elastic)",
            "เขียน Detection Rule และทำ Correlation",
            "ทำ Threat Hunting เบื้องต้น",
            "ปฏิบัติตามขั้นตอน Incident Response (NIST 800-61)",
        ],
        "learningOutcomes": [
            "วิเคราะห์ Log และตรวจจับภัยคุกคาม",
            "ตอบสนองเหตุการณ์ความปลอดภัยอย่างเป็นขั้นตอน",
            "จัดทำรายงานและหลักฐานการสอบสวน",
        ],
        "realWorld": [
            "เฝ้าระวังระบบขององค์กรตลอด 24 ชม.",
            "รับมือ Ransomware / Data Breach",
            "ตรวจสอบพฤติกรรมต้องสงสัยในเครือข่าย",
        ],
    },
    35: {  # Penetration Testing & Offensive Security
        "techniques": [
            "ทำ Reconnaissance รวบรวมข้อมูลเป้าหมาย",
            "ใช้ Metasploit/Nmap/Burp ในการทดสอบ",
            "ทำ Privilege Escalation หลังเจาะเข้าได้",
            "เขียน Pentest Report พร้อมแนวทางแก้ไข",
        ],
        "learningOutcomes": [
            "ทดสอบเจาะระบบอย่างเป็นกระบวนการ",
            "ใช้เครื่องมือ Offensive Security ได้",
            "รายงานช่องโหว่และแนะนำการแก้ไข",
        ],
        "realWorld": [
            "ตรวจสอบความแข็งแกร่งของระบบองค์กร",
            "ทดสอบแอป/เครือข่ายก่อนเปิดตัว",
            "ทำงานเป็น Red Team / Bug Bounty",
        ],
    },
    36: {  # Circuit Theory & Electronic Devices
        "techniques": [
            "วิเคราะห์วงจรด้วยกฎของ Kirchhoff (KCL/KVL)",
            "ใช้ Thevenin/Norton ลดรูปวงจร",
            "คำนวณการทำงานของ Transistor และ Op-Amp",
            "ออกแบบ Passive/Active Filter",
        ],
        "learningOutcomes": [
            "วิเคราะห์วงจร AC/DC ได้",
            "ออกแบบวงจรด้วย Transistor/Op-Amp",
            "คำนวณและจำลองวงจรด้วยซอฟต์แวร์",
        ],
        "realWorld": [
            "ออกแบบวงจรควบคุมอุปกรณ์อิเล็กทรอนิกส์",
            "วิเคราะห์และซ่อมวงจรจริง",
            "ออกแบบ Power Supply และ Sensor Interface",
        ],
    },
    37: {  # Digital Logic Design & Hardware Description Language
        "techniques": [
            "ออกแบบ Combinational/Sequential Logic จาก Truth Table",
            "เขียน FSM (State Diagram) ก่อนเขียน HDL",
            "เขียน Verilog/VHDL และจำลองด้วย Simulator",
            "สังเคราะห์และโหลดวงจรลง FPGA",
        ],
        "learningOutcomes": [
            "ออกแบบวงจรดิจิทัลอย่างเป็นระบบ",
            "เขียน HDL และจำลองการทำงานได้",
            "ใช้ FPGA พัฒนาโปรโตไทป์ฮาร์ดแวร์",
        ],
        "realWorld": [
            "ออกแบบชิปและวงจรในอุตสาหกรรม",
            "สร้างโปรโตไทป์ CPU/ระบบฝังตัวบน FPGA",
            "พัฒนาวงจรประมวลผลสัญญาณดิจิทัล",
        ],
    },
    38: {  # Computer Organization & RISC-V Architecture
        "techniques": [
            "เข้าใจวงจร Fetch-Decode-Execute และ Pipelining",
            "วิเคราะห์ Memory Hierarchy: Cache/RAM",
            "เขียน Assembly (RISC-V) เพื่อเข้าใจ ISA",
            "ออกแบบ Datapath และ Control Unit",
        ],
        "learningOutcomes": [
            "อธิบายการทำงานภายใน CPU ได้",
            "เขียนโปรแกรม Assembly RISC-V เบื้องต้น",
            "วิเคราะห์ Performance (CPI, Pipelining)",
        ],
        "realWorld": [
            "ออกแบบระบบคอมพิวเตอร์และชิป",
            "ทำ Low-level Optimization สำหรับ Embedded",
            "พัฒนา Driver และระบบที่ใกล้ Hardware",
        ],
    },
    39: {  # Embedded Systems & Real-Time OS (RTOS)
        "techniques": [
            "เขียนโปรแกรมควบคุม MCU ด้วย C/C++ และ HAL",
            "จัดการ Interrupt และ Timer อย่างถูกต้อง",
            "ใช้ DMA เพื่อไม่ให้ CPU รอข้อมูล",
            "ออกแบบ Task บน FreeRTOS ด้วย Priority",
        ],
        "learningOutcomes": [
            "พัฒนาโปรแกรมบน STM32/ESP32",
            "จัดการการทำงานแบบ Real-time ได้",
            "เชื่อมต่อเซนเซอร์และแอคชูเอเตอร์",
        ],
        "realWorld": [
            "พัฒนา IoT Device และสมาร์ทโฮม",
            "สร้างระบบควบคุมในรถยนต์/โรงงาน",
            "ออกแบบ Wearable และอุปกรณ์การแพทย์",
        ],
    },
    40: {  # IoT Hardware Interfaces & Protocols
        "techniques": [
            "สื่อสารด้วย UART/SPI/I2C ให้เหมาะกับอุปกรณ์",
            "เชื่อมต่อกับ Cloud ด้วย MQTT",
            "ใช้ CoAP/Zigbee/Modbus ตามงานอุตสาหกรรม",
            "จัดการพลังงานและความน่าเชื่อถือของ Node",
        ],
        "learningOutcomes": [
            "เชื่อมต่อเซนเซอร์ผ่าน Hardware Interface ได้",
            "ส่งข้อมูล IoT ผ่าน MQTT/CoAP",
            "ออกแบบระบบ IoT ตั้งแต่ Node ถึง Cloud",
        ],
        "realWorld": [
            "สร้างระบบ Smart Farm / Smart City",
            "ทำระบบ Monitor เครื่องจักรในโรงงาน",
            "พัฒนา IoT Platform ที่เชื่อมต่ออุปกรณ์หลายชนิด",
        ],
    },
}


def main() -> None:
    conn = get_db()
    updated = 0
    try:
        with conn.cursor() as cur:
            for node_id, content in NODE_DETAILS.items():
                cur.execute(
                    """
                    UPDATE nodes
                    SET techniques = %s,
                        learning_outcomes = %s,
                        real_world = %s
                    WHERE id = %s
                      AND (techniques = '[]'
                           OR learning_outcomes = '[]'
                           OR real_world = '[]')
                    """,
                    (
                        json.dumps(content["techniques"], ensure_ascii=False),
                        json.dumps(content["learningOutcomes"], ensure_ascii=False),
                        json.dumps(content["realWorld"], ensure_ascii=False),
                        node_id,
                    ),
                )
                updated += cur.rowcount
        conn.commit()
        print(f"Updated {updated} node(s) with teaching details.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
