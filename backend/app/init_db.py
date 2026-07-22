import asyncio
from sqlalchemy import select
from app.infrastructure.database import engine, AsyncSessionLocal
from app.domain.models import Base, User, Tenant, RoleEnum
from app.core.security import get_password_hash

async def init_db():
    print("Connecting to database...")
    async with engine.begin() as conn:
        print("Running create_all...")
        await conn.run_sync(Base.metadata.create_all)
    
    print("Tables created. Creating default data...")
    async with AsyncSessionLocal() as db:
        # Create default tenant
        tenant_result = await db.execute(select(Tenant).where(Tenant.name == "default"))
        tenant = tenant_result.scalars().first()
        if not tenant:
            tenant = Tenant(name="default")
            db.add(tenant)
            await db.commit()
            await db.refresh(tenant)
            
        # Create default admin user
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
            
    print("Database initialized and admin user created.")
    await engine.dispose()

if __name__ == "__main__":
    print("Starting init_db script...")
    asyncio.run(init_db())
