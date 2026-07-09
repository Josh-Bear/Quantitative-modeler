# CLAUDE CODE PROMPT
# Copy ข้อความด้านล่างทั้งหมดไปวางใน Claude Code

---

## PROMPT TO COPY:

```
Read the file black_litterman_model/FRONTEND_REDESIGN.md completely before doing anything else. Do not start writing code until you have read the entire file.

After reading, implement the React frontend exactly as specified. Follow these rules strictly:

1. Work inside `black_litterman_model/frontend/` only — do not touch `backend/`, `engine/`, or any other directory unless the spec says so
2. Implement in this order, completing each before moving to the next:
   a. package.json + vite.config.ts + tsconfig.json
   b. src/types.ts — all interfaces from §4
   c. src/api/client.ts — all fetch methods from §5
   d. src/store/marketStore.ts, viewsStore.ts, resultsStore.ts — from §6
   e. src/engine/index.ts — wrapper from §8
   f. src/components/ — Navbar, ChipInput, SliderRow, ViewCard, PreviewTable, WeightChart, FrontierChart
   g. src/pages/Setup.tsx — from §7.1
   h. src/pages/ManualViews.tsx — from §7.2
   i. src/pages/MLViews.tsx — from §7.3
   j. src/pages/Results.tsx — from §7.4
   k. src/App.tsx + src/main.tsx — routing from §3
   l. frontend/index.html — include BL engine script tags from §8
   m. frontend/Dockerfile — from §9
   n. Update docker-compose.yml frontend service — from §9

3. Do not add any library not listed in the spec §1
4. Do not use localStorage anywhere
5. Use the TypeScript types from types.ts everywhere — no `any` except in engine/index.ts wrapper
6. Every constant value (CONFIDENCE, Q_FLOOR, Q_CAP, ML_Q_CLAMP, API_BASE) must match §10 exactly
7. After finishing all files, verify the Definition of Done checklist in §12
```

---

## วิธีใช้

1. เปิด Claude Code ใน terminal:
```bash
cd /Users/doyinratnavardhana/Quantitative-modeler
claude
```

2. Copy prompt ด้านบน (ระหว่าง ``` อยู่) วางใน Claude Code แล้วกด Enter

3. Claude Code จะอ่าน FRONTEND_REDESIGN.md ก่อน แล้ว implement ทีละขั้น

4. หลัง Claude Code เสร็จแล้ว — ให้กลับมาถามผมตรวจก่อน build จริง

---

## Prompt ตรวจงานหลัง Claude Code เสร็จ (ใช้กับผม ไม่ใช้กับ Claude Code)

```
Claude Code เพิ่งสร้าง React frontend ใน black_litterman_model/frontend/ เสร็จแล้ว
ช่วย recheck ทุกไฟล์เทียบกับ FRONTEND_REDESIGN.md หน่อย — เน้นตรวจ:
1. types.ts ครบทุก interface ไหม
2. store แต่ละตัว actions ครบไหม
3. MLViews.tsx มี parseMLViews, r̂ table, clearMLViews ไหม
4. BL compute flow ใน ManualViews ถูก sequence ไหม
5. engine/index.ts โหลด window.BL ได้จริงไหม
6. docker-compose.yml frontend service อัพเดทแล้วไหม
```
