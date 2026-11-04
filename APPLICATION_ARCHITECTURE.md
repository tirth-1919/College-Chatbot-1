# Application Architecture Report

## Final Implementation Status (2026-11-02)

### Implementation Summary

The User/Admin application separation has been successfully completed. Both applications now run independently with their own backend and frontend processes, using separate ports and CORS configurations while sharing the same database for college knowledge.

### Architecture Overview

| Application | Backend Entry Point | Backend Port | Frontend Directory | Frontend Port | API Base URL |
| --- | --- | --- | --- | --- | --- |
| User | `backend/app/user_main:app` | 8000 | `frontend/user-app` | 3000 | `http://127.0.0.1:8000/api/v1` |
| Admin | `backend/app/admin_main:app` | 8001 | `frontend/admin-app` | 3001 | `http://127.0.0.1:8001/api/v1` |

### Key Components

#### Backend Separation

- **User Backend**: `backend/app/user_main.py` - Imports `create_application("user")` from `application_factory.py`
- **Admin Backend**: `backend/app/admin_main.py` - Imports `create_application("admin")` from `application_factory.py`
- **Application Factory**: `backend/app/application_factory.py` - Creates independent FastAPI applications with:
  - Side-specific CORS allowlists (port 3000 for User, port 3001 for Admin)
  - Route filtering based on path prefixes
  - Shared database models and services
  - Independent `/health` endpoints

#### Frontend Separation

- **User Frontend**: `frontend/user-app/` - Complete Next.js application with:
  - Independent `package.json` and `next.config.ts`
  - Build output directory: `.next-user`
  - Environment variable: `NEXT_PUBLIC_APP_SIDE=user`
  - API URL: `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000/api/v1`

- **Admin Frontend**: `frontend/admin-app/` - Complete Next.js application with:
  - Independent `package.json` and `next.config.ts`
  - Build output directory: `.next-admin`
  - Environment variable: `NEXT_PUBLIC_APP_SIDE=admin`
  - API URL: `NEXT_PUBLIC_ADMIN_API_URL=http://127.0.0.1:8001/api/v1`

#### Startup Scripts

- **User Launcher**: `user.py` - Starts User Backend (8000) and User Frontend (3000)
- **Admin Launcher**: `admin.py` - Starts Admin Backend (8001) and Admin Frontend (3001)
- **Server Manager**: `server_manager.py` - Robust process management with:
  - Health check waiting
  - Port conflict detection
  - Automatic restart on crash
  - Clean shutdown handling

#### Environment Configuration

- **User Config**: `.env.user` - Contains `APP_SIDE=user` and `CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000`
- **Admin Config**: `.env.admin` - Contains `APP_SIDE=admin` and `CORS_ORIGINS=http://localhost:3001,http://127.0.0.1:3001`
- **Shared Config**: `.env` - Contains database credentials, API keys, and other shared settings

### Database Architecture

Both applications share the same SQLite database (`backend/chatbot.db`) which contains:
- Shared college knowledge (Colleges, Facts, Pages, MediaAssets)
- User data (Users, Conversations, Messages)
- Admin data (CollegeDocuments, DocumentStagedRow, CrawlJobs)
- Audit logs and analytics

**Access Control**:
- User Backend: Read-only access to published/verified knowledge
- Admin Backend: Full management access with role-based permissions
- Tenant isolation enforced via `college_id` and `effective_college_id`
- Pending review documents not exposed to users as verified knowledge

### API Route Separation

**User Routes** (exposed on port 8000):
- `/auth/*` - Authentication (signup, login, logout, MFA)
- `/conversations/*` - Chat conversations and history
- `/chat` - Chat endpoint
- `/feedback` - User feedback
- `/colleges/*` - College listing and resolution
- `/registrations/*` - College registration
- `/account/*` - User profile and data export
- `/widget/*` - Widget API

**Admin Routes** (exposed on port 8001):
- `/auth/*` - Admin authentication
- `/admin/*` - College management, crawler, knowledge gaps, analytics
- `/super/*` - Super admin overview and settings
- `/api/v1/admin/*` - Document upload, media management, sources
- `/api/v1/super-admin/*` - Document approval workflow
- `/api/v1/local-file/*` - Local file serving

### Testing Results

#### Independent Startup Tests

✅ **User Application**: Successfully starts on ports 8000 (backend) and 3000 (frontend)
✅ **Admin Application**: Successfully starts on ports 8001 (backend) and 3001 (frontend)

#### Simultaneous Startup Test

✅ **Both Applications**: Successfully run simultaneously without conflicts
- Port 3000: User Frontend (PID 5660)
- Port 3001: Admin Frontend (PID 16228)
- Port 8000: User Backend (PID 23292)
- Port 8001: Admin Backend (PID 12984)

### Critical Bugs Fixed

1. **Request Parameter Defaults**: Fixed `Request=Request({})` default values that caused KeyError on import
2. **Parameter Ordering**: Fixed parameter ordering to match FastAPI dependency injection requirements
3. **Route Method**: Changed widget chat from GET to POST for proper data handling

### Startup Instructions

**Start User Application:**
```bash
python user.py
```

**Start Admin Application:**
```bash
python admin.py
```

**Stop Applications:**
```bash
python user.py stop
python admin.py stop
```

**Check Status:**
```bash
python user.py status
python admin.py status
```

### Verification Checklist

- ✅ User Backend imports successfully as `app.user_main:app`
- ✅ Admin Backend imports successfully as `app.admin_main:app`
- ✅ User Frontend uses correct API URL (port 8000)
- ✅ Admin Frontend uses correct API URL (port 8001)
- ✅ CORS configured separately for each application
- ✅ Both applications can run simultaneously
- ✅ No port conflicts detected
- ✅ Health endpoints accessible on both backends
- ✅ Shared database preserved and accessible to both applications

### Remaining Considerations

1. **Frontend Content**: Both user-app and admin-app currently share the same page.tsx source. They rely on `NEXT_PUBLIC_APP_SIDE` environment variable to determine which UI to render. Consider separating the actual UI components if needed.

2. **Authentication Testing**: Manual testing of login flows, tenant isolation, and role-based access should be performed to verify security.

3. **Smart Upload Testing**: Document upload and approval workflow should be tested to ensure pending documents are not exposed to users.

4. **Crawler Testing**: Website crawler functionality should be tested to ensure it works correctly in the Admin application.

5. **Production Deployment**: Environment-specific configurations (e.g., PostgreSQL vs SQLite, production CORS origins) should be configured for production deployment.
