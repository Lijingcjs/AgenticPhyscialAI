# Python Script, API Version = V241
"""Test-only: make a disposable CAD copy and optionally leave a real group edit unsaved."""
import json
import os
import traceback

execfile(os.environ["CFD_AGENT_SC_COMMON"], globals())
execfile(os.environ["CFD_AGENT_SC_SAVE"], globals())
from SpaceClaim.Api.V241 import Group, IDocObject
from SpaceClaim.Api.V241.Scripting.Commands import DocumentOpen, DocumentSave
from System.Collections.Generic import List

with open(os.environ["CFD_AGENT_SC_BUILD_REQUEST"], "r") as stream:
    request = json.load(stream)
result = {"ok": False}
try:
    DocumentOpen.Execute(request["input"])
    DocumentSave.Execute(request["output"])
    document = Window.ActiveWindow.Document
    result["saved_initially_modified"] = bool(document.IsModified)
    if request["make_edit"]:
        faces = list(DocumentHelper.GetRootPart().GetAllBodies())[0].Faces
        Group.Create(DocumentHelper.GetRootPart(), request["group_name"], List[IDocObject]([faces[0]]))
    result["modified_after_edit"] = bool(document.IsModified)
    result["save_bridge"] = install_save_bridge(document, request["output"], request["folder"])
    result["ok"] = True
except Exception:
    result["error"] = traceback.format_exc()
temporary = request["response"] + ".tmp"
with open(temporary, "w") as stream:
    json.dump(result, stream, indent=2)
os.rename(temporary, request["response"])
