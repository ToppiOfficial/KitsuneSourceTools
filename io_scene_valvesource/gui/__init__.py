#  Copyright (c) 2014 Tom Edwards contact@steamreview.org
#
# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# Reload submodules when the package is reloaded
# Import order follows the dependency chain: helpers first, then consumers.
if "bpy" in dir():
    import importlib
    from . import helpers, uilists, operators, panels, menus, pie
    for _mod in [helpers, uilists, operators, panels, menus, pie]:
        importlib.reload(_mod)
else:
    from . import helpers, uilists, operators, panels, menus, pie

# Re-export everything so the parent package can still use `GUI.ClassName`.
from .helpers import _draw_proc_bone_context_menu, _mesh_type_allows
from .uilists import *
from .operators import *
from .panels import *
from .menus import *
from .pie import *
