"""Which computer is this? Everything that differs between Mac and Windows asks here, so the shared code stays shared."""
import sys

IS_MAC = sys.platform == 'darwin'
IS_WIN = sys.platform.startswith('win')
NAME = 'mac' if IS_MAC else 'windows' if IS_WIN else 'other'
