import os


# Tests are deterministic and never consume live market or Qwen API quotas.
os.environ["DATA_PROVIDER"] = "mock"
os.environ["DATABASE_PATH"] = ":memory:"
os.environ["QWEN_ENABLED"] = "false"
os.environ.pop("DASHSCOPE_API_KEY", None)
