"""模块层：模块注册表、Action 原语与业务模块。

import 所有子模块以触发 @register_action 注册。
新增业务模块时，在这里追加一行 import 即可。
"""

from . import actions  # noqa: F401
from . import arena  # noqa: F401
from . import base  # noqa: F401
from . import battle  # noqa: F401
from . import clicker  # noqa: F401
from . import daily  # noqa: F401
from . import fishing  # noqa: F401
from . import guild  # noqa: F401
from . import navigation  # noqa: F401
from . import qunxiong  # noqa: F401
from . import smoke  # noqa: F401
