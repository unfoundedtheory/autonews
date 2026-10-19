"""Vercel-recognized FastAPI entrypoint with explicit /api routing."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from utbot.web import app as newsroom

@asynccontextmanager
async def lifespan(app):
    async with newsroom.router.lifespan_context(newsroom):
        yield

app=FastAPI(title='Unfounded Theory Automation', lifespan=lifespan)
app.mount('/api',newsroom)

@app.get('/')
def homepage():
    return RedirectResponse('/api/planner',status_code=307)
