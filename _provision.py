"""Provision the private runtime, for testing (NOT part of the app)."""
import app.runtime as runtime
import server.config as config

cfg = config.load()
print("status before:", runtime.status(cfg))
print("ensure:", runtime.ensure(cfg))
print("status after:", runtime.status(cfg))
