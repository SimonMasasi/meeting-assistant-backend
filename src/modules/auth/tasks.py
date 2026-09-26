from src.core.celery_app import celery_app

@celery_app.task(name="auth.send_welcome_email")
def send_welcome_email(email: str):
    # Process email here...
    return f"Welcome email sent to {email}"