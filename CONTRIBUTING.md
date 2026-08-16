# Contributing

ขอบคุณที่ช่วยพัฒนา Enlightenment Compass โปรเจกต์นี้ออกแบบให้กราฟเป็น source
of truth ของเส้นทางเรียน จึงมีข้อควรระวังมากกว่าเว็บ CRUD ทั่วไปเล็กน้อย

## ก่อนเริ่ม

1. อ่าน `README.md` และ `AGENTS.md`
2. สร้าง branch สำหรับงานหนึ่งเรื่อง
3. ตั้ง `.env` ให้ชี้ไปยัง PostgreSQL สำหรับพัฒนา/ทดสอบ ห้ามใช้ production DB
4. รัน tests ก่อนแก้เพื่อบันทึก baseline ของ environment

## Architecture rules

- `node_prerequisites` และ `GraphEngine` เป็นผู้ตัดสิน dependency, status และ path
- AI อ่าน graph และ user profile เพื่ออธิบาย/แนะนำได้ แต่ห้ามสร้างหรือเปลี่ยน edge
- Route module ควรรับและ validate HTTP input แล้วส่งงานที่ใช้ซ้ำไป service/store
- SQL schema และ persistence อยู่ใน `backend/db_store.py` หรือ store ของ domain นั้น
- รักษา API response envelope: `{ "ok": true, ... }` หรือ
  `{ "ok": false, "error": "..." }`
- หลีกเลี่ยงการแก้ template/static/backend หลาย domain ใน PR เดียวโดยไม่จำเป็น

## Code style

- ใช้ Python 3.10+ พร้อม type hints ใน public function ใหม่
- เพิ่ม docstring ให้ module/class และ comment เฉพาะเหตุผลที่โค้ดบอกตัวเองไม่ได้
- ใช้ชื่อภาษาอังกฤษใน code/API และใช้ข้อความไทยได้ใน UI/content
- อย่าเพิ่ม secret, access token, database dump หรือข้อมูลส่วนบุคคลลง Git

## Testing

รัน unit/UI tests ที่ไม่ต้องใช้ DB:

```powershell
python -m unittest -v tests.test_study_buddy_service tests.test_study_buddy_ui tests.test_teaching_assistant
```

เมื่อแก้ graph, store, route หรือ schema ให้รันชุดเต็มกับ test database:

```powershell
python -m unittest discover -v
```

ก่อนส่ง PR โปรดสรุป behavior ที่เปลี่ยน, test ที่รัน และ migration/configuration ที่
ผู้ดูแลต้องทำ พร้อมเพิ่ม tests สำหรับ bug fix หรือ contract ใหม่ทุกครั้งที่ทำได้
