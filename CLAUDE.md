# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AIScheduling is a shift scheduling application for managing employee work schedules with a focus on night shift rotations. The system uses a 3-group rotation pattern (A/B/C groups working 1 day, resting 2 days) and enforces role-based constraints for chief-qualified personnel.

## Architecture

### Monorepo Structure

- **`web/`**: React + TypeScript + Vite frontend application
- **`backend/`**: Python FastAPI backend with OR-Tools constraint solver

### Backend Architecture (`backend/`)

**Tech Stack:**
- Python 3.10+, FastAPI, Google OR-Tools (CP-SAT solver)
- Pandas + OpenPyXL for Excel export
- Pydantic for data validation

**Core Components:**
- `app/main.py`: FastAPI application entry point with CORS middleware
- `app/routers/schedule.py`: API endpoints for generate, validate, export
- `app/services/scheduler.py`: `SchedulingSolver` class using OR-Tools CP-SAT
- `app/services/validator.py`: Schedule validation logic
- `app/services/exporter.py`: Excel export with formatting
- `app/utils/date_utils.py`: Work day calculation using anchor logic
- `app/models/schemas.py`: Pydantic models matching frontend types

**Scheduling Algorithm (CP-SAT Solver):**
1. Decision variables: `x[employee, day, shift_type]` boolean assignments
2. Chief variables: `c[employee, day, shift_type]` for leader assignments
3. Hard constraints:
   - Each employee works exactly one shift per day
   - Each shift type has exact headcount (DAY=6, SLEEP=5, MINI_NIGHT=3, LATE_NIGHT=3)
   - Each night shift has exactly one chief from the 6 leaders
4. Objective: Minimize late night variance + avoidance group penalties

**Slot Configuration (17 total per day):**
- Day shift: 6 regular slots
- Sleep shift: 1 chief + 2 northwest + 2 southeast (5 total)
- Mini night: 1 chief + 2 regular (3 total)
- Late night: 1 chief + 2 regular (3 total)

**Anchor Date Logic:**
- 2024-01-01 is Group A's work day (anchor)
- Groups rotate on 3-day cycle: A works day 0, B works day 1, C works day 2
- `is_work_day(date, group)` calculates: `(date - anchor - group_offset) % 3 == 0`

### Frontend Architecture (`web/`)

**State Management Pattern:**
- Single-source-of-truth state in `App.tsx` using React hooks
- `employees` and `schedules` are the two primary state arrays
- State synchronization via `useEffect` hooks ensures consistency when employees change
- Atomic state updates prevent UI inconsistency during employee add/remove operations

**Core Data Flow:**
1. `App.tsx` maintains global state (employees, schedules, selected month/group)
2. State flows down to three main components via props:
   - `MatrixHeader`: Controls for group selection, month picker, auto-schedule
   - `MatrixGrid`: Main scheduling matrix with drag-and-drop shift swapping
   - `MatrixFooter`: Statistics and conflict display
3. Callbacks flow up from child components to update parent state

**Key Files:**
- `types.ts`: TypeScript definitions for ShiftType, Employee, ShiftRecord, Conflict, DailySchedule
- `data.ts`: Initial employee data and scheduling logic (`generateMonthSchedules`, `autoScheduleRowLogic`)
- `App.tsx`: Main application logic, state management, conflict detection
- `components/MatrixGrid.tsx`: Interactive scheduling grid with drag-and-drop
- `components/MatrixHeader.tsx`: Top navigation and controls
- `components/MatrixFooter.tsx`: Statistics and conflict warnings

**Shift Types:**
- `DAY`: Day shift (白班)
- `SLEEP`: Sleep shift (睡觉)
- `MINI_NIGHT`: Mini night shift (小夜)
- `LATE_NIGHT`: Late night shift (大夜)
- `VACATION`: Vacation (休假)
- `NONE`: No shift assigned

**Business Rules:**
- First 6 employees are chief-qualified (主任资质) and can lead night shifts
- Each night shift type (SLEEP, MINI_NIGHT, LATE_NIGHT) requires exactly one chief
- A/B/C group filtering: Group A works on days where `day % 3 === 1`, Group B on `day % 3 === 2`, Group C on `day % 3 === 0`
- Conflict detection validates chief presence and identifies duplicate chiefs

## Development Commands

### Backend (backend/)

```bash
# Install dependencies
pip install -r requirements.txt

# Run development server (http://localhost:8000)
uvicorn app.main:app --reload

# Run with specific host/port
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**API Endpoints:**
- `POST /api/schedule/generate` - Generate optimized schedule using CP-SAT solver
- `POST /api/schedule/validate` - Validate a single day's schedule
- `POST /api/schedule/export` - Export schedule to Excel file
- `GET /api/schedule/workdays/{month}/{group_id}` - Get work days for month/group

### Frontend (web/)

```bash
# Install dependencies
npm install

# Run development server (http://localhost:3000)
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

### Environment Setup

Create `web/.env.local` with:
```
GEMINI_API_KEY=your_api_key_here
```

The Vite config exposes this as `process.env.GEMINI_API_KEY` and `process.env.API_KEY`.

## Code Patterns

### Adding New Shift Types

1. Add enum value to `ShiftType` in `types.ts`
2. Update `colors` and `labels` objects in `MatrixGrid.tsx` ShiftCell component
3. Update conflict detection logic in `App.tsx` if needed
4. Update statistics calculation in `MatrixFooter.tsx` if the shift should be counted

### Modifying Scheduling Logic

The auto-schedule algorithm is in `data.ts:autoScheduleRowLogic()`. It:
1. Randomly assigns 3 different chiefs to SLEEP, MINI_NIGHT, LATE_NIGHT
2. Randomly distributes remaining employees across shift types
3. Returns an array of ShiftRecords for one day

### State Synchronization

When modifying employee-related state, ensure the `useEffect` in `App.tsx:26-41` properly syncs schedules. The pattern:
- Find existing record for each employee
- Create new record with `ShiftType.NONE` if employee is new
- Preserve existing shift assignments

### Conflict Detection

Conflicts are computed in `App.tsx:119-153` and include:
- `CHIEF_MISSING`: No chief assigned to a night shift
- `CHIEF_DUPLICATE`: Multiple chiefs on same night shift type

Add new conflict types by extending the `Conflict` interface in `types.ts` and updating the detection logic.

## Tech Stack

### Frontend
- **React 19.2.4**: UI framework
- **TypeScript 5.8.2**: Type safety
- **Vite 6.2.0**: Build tool and dev server
- **Tailwind CSS**: Styling (via inline classes)
- **Material Icons**: Icon system (loaded via CDN in index.html)

### Backend
- **Python 3.10+**: Runtime
- **FastAPI**: Web framework
- **OR-Tools**: Google's constraint programming solver (CP-SAT)
- **Pandas + OpenPyXL**: Excel generation
- **Pydantic**: Data validation and serialization

## Important Notes

- The project uses Chinese labels for UI elements (白班, 小夜, 大夜, etc.)
- Grid layout uses CSS Grid with dynamic column count based on employee count
- Drag-and-drop is implemented with native HTML5 drag events
- Initial schedules are empty (`ShiftType.NONE`) each month per requirements
- Backend runs on port 8000, frontend on port 3000 (CORS configured)
- The CP-SAT solver has a 30-second timeout for schedule generation
- Frontend currently uses client-side scheduling; integrate with backend API for production use
