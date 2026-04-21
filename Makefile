SRC := ../kicad-pedal-common/kicad_pedal_common
DST := kicad_pedal_common

# Files from kicad-pedal-common used by this plugin.
# board_adapter.py is a transitive dep of footprint.py — must be included.
# kiutils_board_adapter.py and plugin_utils.py are not used here.
SYNC_FILES := \
	__init__.py \
	board_adapter.py \
	bom.py \
	footprint.py \
	plotting.py

.PHONY: sync test

sync:
	@echo "Syncing kicad_pedal_common from $(SRC)…"
	@for f in $(SYNC_FILES); do \
		cp -v $(SRC)/$$f $(DST)/$$f; \
	done
	@rsync -av --delete $(SRC)/schema/ $(DST)/schema/
	@echo "Done."

test:
	python3 -m pytest tests/ -v
