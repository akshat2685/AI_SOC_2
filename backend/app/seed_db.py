import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from app.infrastructure.database import engine, AsyncSessionLocal
from app.domain.models import (
    Base, User, Tenant, RoleEnum, Asset, Incident, Alert, 
    CriticalityEnum, SeverityEnum, StatusEnum
)
from app.core.security import get_password_hash

async def seed_db():
    print("Connecting to database...")
    async with engine.begin() as conn:
        print("Running create_all...")
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        # Get or Create default tenant
        tenant_result = await db.execute(select(Tenant).where(Tenant.name == "shieldai-ent"))
        tenant = tenant_result.scalars().first()
        if not tenant:
            tenant = Tenant(name="shieldai-ent")
            db.add(tenant)
            await db.commit()
            await db.refresh(tenant)
            print("Created tenant: shieldai-ent")
            
        # Get or Create admin user
        user_result = await db.execute(select(User).where(User.email == "admin"))
        user = user_result.scalars().first()
        if not user:
            user = User(
                email="admin",
                hashed_password=get_password_hash("password"),
                role=RoleEnum.GLOBAL_ADMIN,
                tenant_id=tenant.id
            )
            db.add(user)
            await db.commit()
            print("Created admin user (admin / password)")

        # Seed Assets
        assets_data = [
            {"hostname": "prod-db-01", "ip_address": "10.0.1.15", "asset_type": "Database Server", "criticality": CriticalityEnum.CRITICAL},
            {"hostname": "web-front-01", "ip_address": "10.0.2.10", "asset_type": "Web Server", "criticality": CriticalityEnum.HIGH},
            {"hostname": "employee-laptop-442", "ip_address": "192.168.1.44", "asset_type": "Workstation", "criticality": CriticalityEnum.LOW},
        ]
        
        for a_data in assets_data:
            result = await db.execute(select(Asset).where(Asset.hostname == a_data["hostname"]))
            if not result.scalars().first():
                asset = Asset(**a_data, tenant_id=tenant.id)
                db.add(asset)
        await db.commit()
        print("Seeded assets.")

        # Seed Incidents and Alerts
        incident_result = await db.execute(select(Incident).where(Incident.title == "Suspicious Login from Unknown IP"))
        if not incident_result.scalars().first():
            incident = Incident(
                tenant_id=tenant.id,
                title="Suspicious Login from Unknown IP",
                description="Multiple failed login attempts followed by a successful login from a previously unseen IP address in Russia.",
                severity=SeverityEnum.HIGH,
                status=StatusEnum.OPEN,
                created_at=datetime.now(timezone.utc) - timedelta(hours=2)
            )
            db.add(incident)
            await db.commit()
            await db.refresh(incident)

            alert = Alert(
                tenant_id=tenant.id,
                incident_id=incident.id,
                source="Azure AD",
                rule_name="Impossible Travel",
                description="User logged in from Moscow, Russia 1 hour after logging in from New York, USA.",
                timestamp=datetime.now(timezone.utc) - timedelta(hours=2)
            )
            db.add(alert)
            await db.commit()
            print("Seeded incident and alert.")

    print("Database seeding completed.")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(seed_db())
