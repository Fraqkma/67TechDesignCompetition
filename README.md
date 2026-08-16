# Enlightenment Compass

Enlightenment Compass คือระบบ Learning Skill Tree ที่พัฒนาสำหรับการแข่งขัน
67 Tech Design Competition ช่วยให้ผู้เรียนเลือกเป้าหมายสายอาชีพ วิเคราะห์
Skill Gap และเรียนตามลำดับ prerequisite ที่ถูกต้อง

## หลักการสำคัญ

Graph คือแหล่งข้อมูลจริงเพียงแหล่งเดียวของเส้นทางการเรียนรู้:

- **Skill** คือ Node
- **Prerequisite หรือ Dependency** คือ Edge
- `GraphEngine` ตรวจสอบ prerequisite, สถานะของ Skill และ Learning Path
- AI มีหน้าที่วิเคราะห์ แนะนำ สอน และอธิบายข้อมูลจาก Graph
- AI ห้ามสร้าง แก้ไข หรือลบ prerequisite ด้วยตัวเอง

## ความสามารถของระบบ

- แผนที่ Skill Tree แบบ Interactive แยกตามสายอาชีพ
- สถานะ Skill แบบ `locked`, `available` และ `completed`
- ตรวจสอบ prerequisite และสร้าง Learning Path ด้วย Graph
- วิเคราะห์ Skill Gap และแนะนำ Skill ถัดไป
- สร้างตัวอย่างแผนการเรียนรายสัปดาห์
- ระบบ Profile, EXP, Rank และ Achievement
- AI Chat, Teaching Assistant และการสร้างรูป Profile ด้วย AI
- ระบบ Study Buddy:
  - ค้นหาผู้ใช้และส่งคำขอเป็นเพื่อน
  - แชร์ Learning Path และส่ง Notification
  - สร้างกลุ่มเรียนและ Group Chat
  - World Chat

## เทคโนโลยีที่ใช้

- Python 3.10+
- Flask 3
- PostgreSQL และ `psycopg2`
- Jinja Template, Vanilla JavaScript และ CSS
- bcrypt สำหรับเข้ารหัสรหัสผ่าน
- OpenAI-compatible API สำหรับ Chat และ Image Generation
- Waitress สำหรับรัน Production Server

## โครงสร้างโปรเจกต์

```text
.
├── app.py                         # Flask factory, หน้าเว็บ และ API หลัก
├── backend/
│   ├── graph_engine.py            # ตรวจ Graph และสร้าง Learning Path
│   ├── db_store.py                # Schema, Catalog และ Progress ใน PostgreSQL
│   ├── ai_analyzer.py             # วิเคราะห์ข้อมูลจาก Graph แบบกำหนดผลได้
│   ├── ai_service.py              # เชื่อมต่อ AI Provider
│   ├── teaching_assistant.py      # จัดการ Teaching Chat
│   ├── plan_service.py            # สร้างแผนการเรียนรายสัปดาห์
│   ├── study_buddy_routes.py      # HTTP Routes ของระบบ Social
│   ├── study_buddy_service.py     # Business Logic ของ Study Buddy
│   └── study_buddy_store.py       # จัดเก็บข้อมูล Social
├── data/
│   └── seed_node_details.py       # เติมเนื้อหาประกอบการเรียนให้ Node
├── templates/                     # หน้า HTML แบบ Jinja
├── static/                        # CSS, JavaScript และรูปภาพ
├── tests/                         # Unit Test และ PostgreSQL Integration Test
├── database_schema_description.txt
└── run_windows.bat
```

## วิธีติดตั้งและเริ่มใช้งาน

### 1. Clone Repository

```bash
git clone <repository-url>
cd 67TechDesignCompetition
```

### 2. สร้าง Virtual Environment

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS หรือ Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. ติดตั้ง Dependencies

```bash
python -m pip install -r requirements.txt
```

### 4. ตั้งค่า PostgreSQL

สร้าง PostgreSQL Database และ User ที่มีสิทธิ์สร้างและแก้ไข Table จากนั้นคัดลอก
ไฟล์ตัวอย่าง Environment

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

macOS หรือ Linux:

```bash
cp .env.example .env
```

แก้ไข `.env` และใส่ค่าที่ใช้งานจริง ห้าม Commit ไฟล์นี้ขึ้น Repository

ตัวแปรหลักสำหรับเชื่อมต่อ Database:

```dotenv
SERVER_IP=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_DB_NAME=enlightenment_compass
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-password
```

ระบบรองรับชื่อตัวแปรแบบเดิม ได้แก่ `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`
และ `DB_PASSWORD` แต่ `SERVER_IP` และตัวแปร `POSTGRES_*` จะมีลำดับความสำคัญสูงกว่า
จึงไม่ควรกำหนดค่าของตัวแปรสองชุดให้ขัดแย้งกัน

ระบบจะสร้าง Table และ Built-in Catalog ที่จำเป็นแบบ Idempotent แต่ข้อมูล Career,
Node, Career-Node Mapping และ Prerequisite ต้องมีอยู่ใน PostgreSQL ดูรายละเอียด
โครงสร้างได้ที่
[`database_schema_description.txt`](database_schema_description.txt)

### 5. ตั้งค่า AI (ไม่บังคับสำหรับฟีเจอร์ Graph)

กำหนด `OPENAI_API_KEY` หรือ `AI_API_KEY` และสามารถปรับค่าเพิ่มเติมได้ดังนี้:

```dotenv
AI_MODEL=gpt-4o-mini
AI_IMAGE_MODEL=gpt-image-2
AI_BASE_URL=https://api.openai.com/v1
AI_IMAGE_TIMEOUT_SECONDS=120
```

ฟีเจอร์ Roadmap ที่ใช้ Graph สามารถทำงานได้โดยไม่มี API Key แต่ AI Chat และ
การสร้างรูป Profile จำเป็นต้องเชื่อมต่อ AI Provider ได้

### 6. เริ่มต้น Application

```bash
python app.py
```

เปิด <http://127.0.0.1:5000> ใน Browser

ผู้ใช้ Windows สามารถรัน `run_windows.bat` เพื่อสร้าง Virtual Environment,
ติดตั้ง Dependencies และเริ่ม Server โดยอัตโนมัติ

## เติมรายละเอียดการเรียนให้ Node

หากต้องการเติม Techniques, Learning Outcomes และตัวอย่างการใช้งานจริงให้ Node
ที่มีอยู่แล้ว ให้รันคำสั่ง:

```bash
python data/seed_node_details.py
```

Script นี้ไม่สร้างหรือแก้ไข Prerequisite Edge

## การทดสอบ

รัน Test ทั้งหมด:

```bash
python -m unittest discover -v
```

Test บางส่วนจะเชื่อมต่อ PostgreSQL และเขียนข้อมูลชั่วคราว ควรใช้ Database สำหรับ
ทดสอบโดยเฉพาะและตรวจสอบว่ามี Career และ Graph Data ที่จำเป็นแล้ว

รันเฉพาะ Test ที่ไม่ต้องเชื่อมต่อ Database:

```bash
python -m unittest -v tests.test_study_buddy_service tests.test_study_buddy_ui tests.test_teaching_assistant
```

## ข้อควรระวังด้านความปลอดภัย

- ห้าม Commit `.env`, Password, API Key, Database Dump หรือข้อมูลผู้ใช้
- กำหนด `FLASK_SECRET_KEY` เป็นค่าสุ่มที่ยาวและปลอดภัย
- ใช้ PostgreSQL User ที่มีสิทธิ์เท่าที่จำเป็น
- แยก Development, Test และ Production Database ออกจากกัน
- ไม่ควรเปิด Development Server ให้เข้าถึงจาก Internet โดยตรง

## การร่วมพัฒนา

อ่าน [`CONTRIBUTING.md`](CONTRIBUTING.md) ก่อนแก้ไข Graph Rule, Database Schema
หรือ API Contract ส่วน [`CONTRIBUTE.md`](CONTRIBUTE.md) เป็นไฟล์ทางเลือกที่ลิงก์
มายังคู่มือฉบับเดียวกัน

## License

โปรเจกต์นี้เผยแพร่ภายใต้ [MIT License](LICENSE)
