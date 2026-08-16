# Enlightenment Compass

Learning Skill Tree สำหรับช่วยผู้เรียนวางเส้นทางการเรียนรู้ตามเป้าหมาย โดยใช้
กราฟเป็นแหล่งข้อมูลหลักของทักษะ ความสัมพันธ์ และ prerequisite ส่วน AI มีหน้าที่
วิเคราะห์ช่องว่าง แนะนำขั้นถัดไป และอธิบายข้อมูลจากกราฟเท่านั้น

## ความสามารถหลัก

- Skill Tree แยกตามสายอาชีพ พร้อมสถานะ `locked`, `available`, `completed`
- ตรวจ prerequisite และสร้าง learning path ด้วย `GraphEngine`
- บันทึก progress, EXP, rank และ achievements ของผู้เรียน
- AI analysis, recommendation, chat และ Teaching Assistant ที่อ้างอิงกราฟ
- Profile onboarding และ AI-generated portrait
- Study Buddy: เพื่อน กลุ่มเรียน แชร์เส้นทาง notification และ world chat

## สถาปัตยกรรม

```text
app.py                         # Application factory / WSGI entry point
backend/
  config.py                    # Environment และ Flask configuration
  database.py                  # Lazy PostgreSQL connection pool
  application_services.py      # Graph + progress + profile orchestration
  routes/
    pages.py                   # หน้าเว็บ
    account.py                 # Auth, session, profile, onboarding
    learning.py                # Career, roadmap, plan, progress
    ai.py                      # AI analysis/chat/teaching endpoints
    responses.py               # JSON envelopes และ gzip middleware
  graph_engine.py              # Source of truth ของ prerequisite/path
  db_store.py                  # Schema, seed catalog และ persistence
  study_buddy_*.py             # Social/Study Buddy domain
templates/                     # Jinja HTML
static/                        # CSS, JavaScript และรูปภาพ
tests/                         # Unit และ PostgreSQL integration tests
```

หลักสำคัญคือ prerequisite ต้องมาจาก `node_prerequisites` ใน PostgreSQL และผ่าน
`GraphEngine` เสมอ ห้ามให้ AI สร้างหรือแก้ edge เอง

## Requirements

- Python 3.10+
- PostgreSQL 14+ (หรือรุ่นที่รองรับ SQL ใน `backend/db_store.py`)
- OpenAI-compatible API key หากต้องการ AI chat และ profile portrait

## เริ่มใช้งาน

1. สร้าง virtual environment และติดตั้ง dependency

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   ```

   บน macOS/Linux ใช้ `python3 -m venv .venv` และ
   `source .venv/bin/activate`

2. สร้าง database เปล่าใน PostgreSQL และให้ user มีสิทธิ์สร้าง/แก้ schema

3. คัดลอก `.env.example` เป็น `.env` แล้วใส่ค่าจริง

   ```powershell
   Copy-Item .env.example .env
   ```

4. เริ่มแอป

   ```powershell
   python app.py
   ```

   หรือบน Windows ใช้ `run_windows.bat` ซึ่งจะสร้าง environment และติดตั้ง
   dependencies ให้อัตโนมัติ แอปเปิดที่ <http://127.0.0.1:5000>

`db_store.ensure_schema()` จะสร้างตารางและ seed catalog ที่มากับระบบใน
database-backed request แรกแบบ idempotent แต่ข้อมูล career, node, career-node
mapping และ prerequisite จริงยังต้องมีอยู่ในฐานข้อมูลของโปรเจกต์ ดูโครงสร้างโดยละเอียดใน
`database_schema_description.txt`

หากต้องการเติม teaching detail ของ node ที่มีอยู่แล้ว:

```powershell
python data/seed_node_details.py
```

## Environment variables

ค่าที่จำเป็น:

- `SERVER_IP`, `POSTGRES_PORT`, `POSTGRES_DB_NAME`, `POSTGRES_USER`,
  `POSTGRES_PASSWORD`
- `FLASK_SECRET_KEY` ควรเป็นค่าสุ่มยาวและคงที่ โดยเฉพาะ production

ระบบยังรองรับชื่อ legacy `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`,
`DB_PASSWORD` ส่วน AI ใช้ `OPENAI_API_KEY` (แนะนำ) หรือ `AI_API_KEY` และปรับ
`AI_MODEL`, `AI_IMAGE_MODEL`, `AI_BASE_URL` ได้

## Tests

ชุดที่ไม่ต้องใช้ฐานข้อมูล:

```powershell
python -m unittest -v tests.test_study_buddy_service tests.test_study_buddy_ui tests.test_teaching_assistant
```

ชุดเต็มเป็น integration tests ที่อ่านและเขียน PostgreSQL:

```powershell
python -m unittest discover -v
```

ควรใช้ database สำหรับทดสอบโดยเฉพาะ ถึงแม้ tests จะลบ user ชั่วคราวของตัวเอง
เมื่อจบแล้วก็ตาม

## การร่วมพัฒนา

อ่าน [CONTRIBUTING.md](CONTRIBUTING.md) ก่อนแก้ graph, schema หรือ API contract
และอย่า commit `.env`, API key, password หรือข้อมูลผู้ใช้จริง

## License

repository นี้ยังไม่มีไฟล์ license เจ้าของโครงการควรเลือก license ที่ต้องการ
(เช่น MIT, Apache-2.0 หรือ GPL-3.0) ก่อนเปิดเป็น public เพราะการเผยแพร่ source
โดยไม่มี license ยังไม่ได้ให้สิทธิ์ผู้อื่นนำโค้ดไปใช้ แก้ หรือแจกจ่าย
