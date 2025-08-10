from .factory import create_app
from .settings import settings

# Create the FastAPI app instance by calling the factory
# The authentication is controlled by the NO_AUTH environment variable
app = create_app(no_auth=settings.NO_AUTH)
