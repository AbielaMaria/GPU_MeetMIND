import traceback
import torch
import transformers
from transformers import AutoModel

print("PyTorch:", torch.__version__)
print("Transformers:", transformers.__version__)
print("CUDA available:", torch.cuda.is_available())

try:
    model = AutoModel.from_pretrained(
        "ekacare/parrotlet-a-2.5-pro",
        trust_remote_code=True,
        device_map="auto",
    )
    model.eval()
    print("MODEL LOAD SUCCESSFUL")
    print("Device map:", getattr(model, "hf_device_map", "not available"))
except Exception:
    print("MODEL LOAD FAILED")
    traceback.print_exc()
