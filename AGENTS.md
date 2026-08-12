# AGENTS.md

## Project
Enlightenment Compass — Learning Skill Tree สำหรับ Hackathon

## Goal
สร้างระบบ Learning Skill Tree ที่ช่วยผู้เรียนวางเส้นทางการเรียนรู้ตามเป้าหมาย
โดยใช้ Graph เพื่อจัดการความสัมพันธ์และ prerequisite ของแต่ละ Skill

## Core Architecture
- Skill = Node
- Prerequisite / Dependency = Edge
- Graph Engine เป็น source of truth ของเส้นทางการเรียน
- ห้ามให้ AI สร้างหรือเปลี่ยน prerequisite เองโดยไม่มีข้อมูลจากระบบ

## AI
AI มีหน้าที่:
- วิเคราะห์ Skill Gap ของผู้ใช้
- แนะนำ Skill ถัดไป
- วิเคราะห์เส้นทางการเรียน
- อธิบายเหตุผลของคำแนะนำ
- เป็น AI Assistant ภายในเว็บไซต์

AI ไม่ควรแทนที่ Graph Engine
AI ควรใช้ข้อมูลจาก Graph + User Profile เพื่อสร้างคำแนะนำ

## Development Rules
- ศึกษา codebase เดิมก่อนแก้ไข
- รักษาโครงสร้างเดิมเท่าที่ทำได้
- อย่าลบหรือ rewrite ระบบที่มีอยู่โดยไม่จำเป็น
- อย่าแก้ไฟล์ที่ไม่เกี่ยวข้องกับ task
- ตรวจสอบผลกระทบต่อระบบเดิมก่อนแก้
- เขียน code ให้ทีมอื่นสามารถอ่านและต่อได้
- หากไม่แน่ใจเกี่ยวกับ architecture ให้ถามก่อน

## Current Project Structure
- backend/ → backend logic
- data/ → project data
- static/ → CSS / JS
- templates/ → HTML
- tests/ → tests
- app.py → main application

## Team Development
โปรเจกต์นี้ทำงานหลายคน
ดังนั้นต้องหลีกเลี่ยงการแก้ไขไฟล์ที่ไม่เกี่ยวข้องกับ task
และไม่ควร rewrite ทั้งโปรเจกต์โดยไม่จำเป็น

## Current Status
- Hackathon: ผ่านรอบคัดเลือกแล้ว
- มี prototype/codebase อยู่แล้ว
- ตอนนี้อยู่ในช่วงพัฒนาต่อยอด prototype