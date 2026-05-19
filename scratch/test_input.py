from textual.widgets import Input
from textual.validation import ValidationResult

# Create dummy input
inp = Input()
event = Input.Submitted(inp, "test-value")

print("Instance attributes of Input.Submitted event:")
for attr in dir(event):
    if not attr.startswith("_"):
        print(f"  - {attr}: {getattr(event, attr)}")
