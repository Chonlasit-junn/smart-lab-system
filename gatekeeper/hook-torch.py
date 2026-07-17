import sys
import os

# Add the _internal folder to sys.path so torch can find its libs
if getattr(sys, 'frozen', False):
    base = sys._MEIPASS
    if base not in sys.path:
        sys.path.insert(0, base)
    # Also add torch lib path explicitly
    torch_lib = os.path.join(base, 'torch', 'lib')
    if os.path.exists(torch_lib) and torch_lib not in sys.path:
        sys.path.insert(0, torch_lib)
    # Add to PATH so DLLs are found
    os.environ['PATH'] = base + os.pathsep + os.environ.get('PATH', '')
    if os.path.exists(torch_lib):
        os.environ['PATH'] = torch_lib + os.pathsep + os.environ['PATH']
