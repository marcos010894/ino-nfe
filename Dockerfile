FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app

# Install backend dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist ./frontend_dist

# Copy SQLite DB directory
# We will use SQLite for now as it's an MVP.
COPY backend/innonfe.db ./

# Modify main.py to serve the frontend dist folder if we want to serve them together
# We will just expose the FastAPI port

ENV PORT=8080
EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
