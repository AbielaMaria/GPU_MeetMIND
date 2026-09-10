import gc
import time
import torch
from transformers import AutoModel


MODEL_NAME = "ekacare/parrotlet-a-2.5-pro"


# ---------------------------------------------------------
# Utility functions
# ---------------------------------------------------------

def gb(value):
    return value / (1024 ** 3)


def gpu_info(label=""):
    torch.cuda.synchronize()

    free, total = torch.cuda.mem_get_info()

    allocated = torch.cuda.memory_allocated()
    reserved = torch.cuda.memory_reserved()
    peak_allocated = torch.cuda.max_memory_allocated()
    peak_reserved = torch.cuda.max_memory_reserved()

    print()
    print("=" * 70)
    print(f"GPU MEMORY — {label}")
    print("=" * 70)

    print(f"Physical GPU memory : {gb(total):.2f} GB")
    print(f"Physical GPU free   : {gb(free):.2f} GB")
    print(f"Physical GPU used   : {gb(total - free):.2f} GB")

    print()
    print(f"PyTorch allocated   : {gb(allocated):.2f} GB")
    print(f"PyTorch reserved    : {gb(reserved):.2f} GB")

    print()
    print(f"Peak allocated      : {gb(peak_allocated):.2f} GB")
    print(f"Peak reserved       : {gb(peak_reserved):.2f} GB")

    print("=" * 70)


def parameter_memory(module):
    """
    Calculate memory occupied by parameters of a module.
    """
    total_bytes = 0
    parameter_count = 0

    for param in module.parameters():
        parameter_count += param.numel()
        total_bytes += param.numel() * param.element_size()

    return parameter_count, total_bytes


def module_report(name, module):
    params, memory = parameter_memory(module)

    print()
    print("-" * 70)
    print(name)
    print("-" * 70)
    print(f"Parameters : {params:,}")
    print(f"Memory     : {gb(memory):.2f} GB")
    print(f"Dtype      : {next(module.parameters()).dtype}")
    print(f"Device     : {next(module.parameters()).device}")


def tensor_report(name, tensor):
    if tensor is None:
        print(f"{name:<35} None")
        return

    memory = tensor.numel() * tensor.element_size()

    print(
        f"{name:<35} "
        f"shape={str(tuple(tensor.shape)):<30} "
        f"dtype={str(tensor.dtype):<15} "
        f"memory={gb(memory):.4f} GB"
    )


# ---------------------------------------------------------
# Start
# ---------------------------------------------------------

print()
print("=" * 70)
print("PARROTLET GPU MEMORY BREAKDOWN")
print("=" * 70)

print(f"Model: {MODEL_NAME}")

if not torch.cuda.is_available():
    print("\nERROR: CUDA is not available.")
    raise SystemExit(1)

print()
print("GPU:")
print(torch.cuda.get_device_name(0))

props = torch.cuda.get_device_properties(0)

print(f"Total VRAM: {gb(props.total_memory):.2f} GB")

# Reset memory statistics
torch.cuda.reset_peak_memory_stats()
torch.cuda.empty_cache()

gpu_info("Initial state")


# ---------------------------------------------------------
# Load model
# ---------------------------------------------------------

print()
print("=" * 70)
print("LOADING PARROTLET")
print("=" * 70)

start = time.time()

model = AutoModel.from_pretrained(
    MODEL_NAME,
    trust_remote_code=True,
    device_map="auto",
)

load_time = time.time() - start

print(f"\nModel loading time: {load_time:.2f} seconds")

gpu_info("After model loading")


# ---------------------------------------------------------
# Model information
# ---------------------------------------------------------

print()
print("=" * 70)
print("MODEL STRUCTURE")
print("=" * 70)

print(f"Model class : {type(model)}")

print(
    f"Model dtype : "
    f"{next(model.parameters()).dtype}"
)

print()


# ---------------------------------------------------------
# Individual component memory
# ---------------------------------------------------------

print("=" * 70)
print("INDIVIDUAL COMPONENT MEMORY")
print("=" * 70)

components = []

if hasattr(model, "encoder"):
    components.append(("ENCODER", model.encoder))

if hasattr(model, "projector"):
    components.append(("PROJECTOR", model.projector))

if hasattr(model, "decoder"):
    components.append(("DECODER", model.decoder))

for name, module in components:
    module_report(name, module)


# ---------------------------------------------------------
# Total parameter memory
# ---------------------------------------------------------

print()
print("=" * 70)
print("TOTAL MODEL PARAMETER MEMORY")
print("=" * 70)

total_params = 0
total_bytes = 0

for param in model.parameters():
    total_params += param.numel()
    total_bytes += param.numel() * param.element_size()

print(f"Total parameters : {total_params:,}")
print(f"Parameter memory : {gb(total_bytes):.2f} GB")

print()
print(
    f"Expected FP16 parameter memory "
    f"(approximately): {gb(total_bytes / 2):.2f} GB"
)

print(
    f"Expected BF16 parameter memory "
    f"(approximately): {gb(total_bytes / 2):.2f} GB"
)


# ---------------------------------------------------------
# Component percentages
# ---------------------------------------------------------

print()
print("=" * 70)
print("COMPONENT MEMORY PERCENTAGE")
print("=" * 70)

for name, module in components:
    params, memory = parameter_memory(module)

    percentage = (
        memory / total_bytes * 100
        if total_bytes > 0
        else 0
    )

    print(
        f"{name:<15} "
        f"{gb(memory):>8.2f} GB   "
        f"{percentage:>6.2f}%"
    )


# ---------------------------------------------------------
# Check all parameter dtypes
# ---------------------------------------------------------

print()
print("=" * 70)
print("PARAMETER DTYPE DISTRIBUTION")
print("=" * 70)

dtype_stats = {}

for param in model.parameters():
    dtype = str(param.dtype)

    if dtype not in dtype_stats:
        dtype_stats[dtype] = {
            "parameters": 0,
            "bytes": 0,
        }

    dtype_stats[dtype]["parameters"] += param.numel()
    dtype_stats[dtype]["bytes"] += (
        param.numel() * param.element_size()
    )


for dtype, values in dtype_stats.items():

    print(
        f"{dtype:<15} "
        f"{values['parameters']:,} parameters   "
        f"{gb(values['bytes']):.2f} GB"
    )


# ---------------------------------------------------------
# Device distribution
# ---------------------------------------------------------

print()
print("=" * 70)
print("PARAMETER DEVICE DISTRIBUTION")
print("=" * 70)

device_stats = {}

for param in model.parameters():

    device = str(param.device)

    if device not in device_stats:
        device_stats[device] = {
            "parameters": 0,
            "bytes": 0,
        }

    device_stats[device]["parameters"] += param.numel()
    device_stats[device]["bytes"] += (
        param.numel() * param.element_size()
    )


for device, values in device_stats.items():

    print(
        f"{device:<15} "
        f"{values['parameters']:,} parameters   "
        f"{gb(values['bytes']):.2f} GB"
    )


# ---------------------------------------------------------
# Sampling rate
# ---------------------------------------------------------

print()
print("=" * 70)
print("AUDIO CONFIGURATION")
print("=" * 70)

print(
    "Sampling rate:",
    getattr(model, "sampling_rate", "NOT FOUND")
)

print(
    "Audio token:",
    getattr(model, "audio_token", "NOT FOUND")
)


# ---------------------------------------------------------
# Empty CUDA cache
# ---------------------------------------------------------

print()
print("=" * 70)
print("CUDA MEMORY AFTER CACHE CLEANUP")
print("=" * 70)

gc.collect()
torch.cuda.empty_cache()

gpu_info("After empty_cache()")


# ---------------------------------------------------------
# Final summary
# ---------------------------------------------------------

print()
print()
print("=" * 70)
print("FINAL SUMMARY")
print("=" * 70)

free, total = torch.cuda.mem_get_info()

print(f"GPU                  : {torch.cuda.get_device_name(0)}")
print(f"Physical VRAM        : {gb(total):.2f} GB")
print(f"Physical VRAM used   : {gb(total - free):.2f} GB")
print(f"Physical VRAM free   : {gb(free):.2f} GB")
print(f"Model parameters     : {gb(total_bytes):.2f} GB")
print(f"Model parameters FP16: {gb(total_bytes / 2):.2f} GB")

print()
print("IMPORTANT:")
print("The parameter memory above is the memory occupied by model weights.")
print("The difference between physical GPU usage and parameter memory")
print("comes from tensors, CUDA workspaces, allocator overhead,")
print("buffers, caches, and other runtime allocations.")

print("=" * 70)
print("DIAGNOSTIC COMPLETE")
print("=" * 70)