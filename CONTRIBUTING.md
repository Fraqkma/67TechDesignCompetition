# คู่มือการร่วมพัฒนา Enlightenment Compass

ขอบคุณที่สนใจช่วยพัฒนา Enlightenment Compass โปรเจกต์นี้ประกอบด้วย Learning
Graph, Progress ของผู้เรียน, AI Assistant และระบบ Social การเปลี่ยนแปลงเพียง
จุดเดียวจึงอาจส่งผลต่อหลายส่วนของระบบ กรุณารักษาขอบเขตของงานและกฎทาง
Architecture ด้านล่าง

## ก่อนเริ่มพัฒนา

1. อ่าน `README.md` และ `AGENTS.md`
2. สร้าง Branch สำหรับงานหนึ่งเรื่อง
3. ตั้งค่า PostgreSQL สำหรับ Development โดยไม่ใช้ข้อมูล Production
4. รัน Test ที่เกี่ยวข้องก่อนแก้ไขเพื่อบันทึก Baseline

## กฎด้าน Architecture

### Graph เป็นแหล่งข้อมูลหลัก

- Skill คือ Node และ Prerequisite คือ Edge
- `backend/graph_engine.py` เป็นผู้กำหนดว่า Skill มีสถานะ `locked`, `available`
  หรือ `completed` และเป็นผู้สร้าง Learning Path
- ข้อมูล Prerequisite ต้องมาจาก PostgreSQL ผ่าน `backend/db_store.py`
- AI อ่านผลจาก Graph และข้อมูลผู้เรียนเพื่อวิเคราะห์หรืออธิบายได้
- AI ห้ามสร้าง ลบ หรือเปลี่ยน Edge และห้ามข้ามกฎของ `GraphEngine`

เมื่อต้องเพิ่มระบบ Recommendation ให้คำนวณตัวเลือกที่ถูกต้องด้วย Graph ก่อน
จากนั้นจึงให้ AI อธิบายผลลัพธ์ดังกล่าว

### แยกความรับผิดชอบของโค้ด

- การรับ Request, Validate Input และสร้าง Response อยู่ใน Route
- Logic ที่ใช้ซ้ำและเกี่ยวข้องกับ Graph อยู่ใน Service
- SQL และ Persistence อยู่ใน Store ของ Domain ที่เกี่ยวข้อง
- พฤติกรรมหน้าเว็บอยู่ใน `static/js`
- Layout และการแสดงผลอยู่ใน Template และ CSS
- รักษารูปแบบ API Response เดิม:

  ```json
  {"ok": true, "data": {}}
  ```

  ```json
  {"ok": false, "error": "ข้อความอธิบายข้อผิดพลาด"}
  ```

## การตั้งค่า Development Environment

สร้าง Virtual Environment และติดตั้ง Dependencies:

```bash
python -m venv .venv
python -m pip install -r requirements.txt
```

คัดลอก `.env.example` เป็น `.env` และใช้ Development Database ระบบเลือก
`SERVER_IP` และตัวแปร `POSTGRES_*` ก่อนตัวแปร Legacy `DB_*` จึงไม่ควรกำหนด
ค่าของสองชุดให้ขัดแย้งกัน

## แนวทางการเขียนโค้ด

- รองรับ Python 3.10 ขึ้นไป
- เพิ่ม Type Hint ให้ Public Function ใหม่เมื่อเหมาะสม
- เพิ่ม Docstring ให้ Module, Class และ Public Function
- Comment เพื่ออธิบายเหตุผลของ Logic ที่ไม่ชัดเจน ไม่ต้องอธิบายทุกบรรทัด
- ใช้ชื่อ Identifier ภาษาอังกฤษ และใช้ภาษาไทยในข้อความสำหรับผู้ใช้ได้
- จำกัด Pull Request ให้อยู่ใน Domain เดียวและหลีกเลี่ยงการ Rewrite ส่วนอื่น
- รักษา Endpoint และ Response Field เดิม ยกเว้นงานนั้นตั้งใจเป็น Breaking Change
- ห้ามซ่อน Graph Rule ไว้ใน Prompt หรือคำตอบที่ AI สร้าง

## การแก้ไข Database

เมื่อเปลี่ยน Schema:

1. อัปเดต Schema Logic แบบ Idempotent ใน `backend/db_store.py`
2. อัปเดต `database_schema_description.txt`
3. รักษาข้อมูลเดิมและทำให้ Migration รันซ้ำได้อย่างปลอดภัย
4. เพิ่ม Test สำหรับ Migration, Constraint และ Store Behavior
5. ห้าม Commit Database Dump ที่มีข้อมูลจริง

การแก้ `node_prerequisites` ต้องได้รับการตรวจสอบเป็นพิเศษ เพราะส่งผลต่อ
Learning Path, Analysis, Recommendation, Planning และ Study Buddy

## การทดสอบ

ระหว่างพัฒนาสามารถรัน Test ที่ไม่ต้องเชื่อมต่อ Database:

```bash
python -m unittest -v tests.test_study_buddy_service tests.test_study_buddy_ui tests.test_teaching_assistant
```

ก่อนส่งงานที่แก้ Route, Store, Graph Behavior หรือ Schema ให้รัน Test ทั้งหมดกับ
Test Database โดยเฉพาะ:

```bash
python -m unittest discover -v
```

เพิ่มหรือแก้ Test สำหรับ Bug Fix และ Behavior ใหม่ทุกครั้ง หาก Integration Test
รันไม่ได้เพราะบริการภายนอกไม่พร้อม ให้ระบุข้อจำกัดใน Pull Request และห้ามรายงาน
ว่า Test ผ่าน

## Commit Message

ใช้ข้อความสั้น กระชับ และบอกสิ่งที่เปลี่ยน แนะนำรูปแบบ Conventional Commits:

```text
feat: add career comparison endpoint
fix: preserve progress when switching tracks
refactor: split profile routes from app factory
docs: expand PostgreSQL setup guide
test: cover invalid prerequisite removal
```

## Checklist ก่อนส่ง Pull Request

- [ ] การเปลี่ยนแปลงมีขอบเขตชัดเจนและไม่ Rewrite ไฟล์ที่ไม่เกี่ยวข้อง
- [ ] การตัดสินใจเกี่ยวกับเส้นทางเรียนยังมาจาก `GraphEngine` และ Edge ในระบบ
- [ ] ตรวจสอบผลกระทบต่อ API และ UI เดิมแล้ว
- [ ] อัปเดตเอกสาร Schema เมื่อมีการเปลี่ยน Database
- [ ] เพิ่มและรัน Test ที่เกี่ยวข้องแล้ว
- [ ] ไม่มี Secret, ข้อมูลส่วนบุคคล, Cache หรือ Database Dump ใน Commit
- [ ] อธิบาย Configuration หรือ Deployment Change แล้ว

## ความปลอดภัย

ห้ามเปิด Public Issue ที่มี Credential, ข้อมูลผู้ใช้ หรือรายละเอียดช่องโหว่ของ
Production โดยตรง ลบข้อมูลสำคัญออกจาก Log และ Screenshot ก่อนแนบใน Issue หรือ
Pull Request

## License

การส่ง Contribution หมายความว่าคุณยอมรับให้ Contribution ดังกล่าวเผยแพร่ภายใต้
[MIT License](LICENSE) ของโปรเจกต์
