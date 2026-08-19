import functools
import traceback

from vanilla import Group, ComboBox, TextBox, Slider, EditText, PopUpButton, Button
from GlyphsApp.UI import GlyphView
from GlyphsApp import Message
from AppKit import NSColor
from HTLSLibrary import HTLSEngine


def guarded(method):
	"""Keep exceptions out of vanilla's callback machinery, which reports them as a plug-in crash."""
	@functools.wraps(method)
	def wrapper(self, *args, **kwargs):
		try:
			return method(self, *args, **kwargs)
		except Exception:
			print("HTLS Manager: error while running %s\n%s" % (method.__name__, traceback.format_exc()))
	return wrapper


def text(value):
	"""Text fields need a string: handing AppKit a number raises deep inside the text system."""
	if value is None:
		return ""
	return str(value)


def sidebearing(layer, side):
	"""LSB/RSB are None on layers without outlines."""
	if layer is None:
		return ""
	value = layer.LSB if side == "LSB" else layer.RSB
	return text(value)


class HTLSGlyphView:
	def __init__(self, parent, glyph_name, glyphs, master):
		if glyph_name not in glyphs:
			glyph_name = glyphs[0].name
		self.parent = parent
		self.glyphs = glyphs
		self.glyph = glyphs[glyph_name]
		# kept as a plain string so it survives the font being closed
		self.glyph_name = self.glyph.name
		self.master = master
		self.layer = self.glyph.layers[master.id]
		# add a group with the following elements: a GlyphView, a ComboBox to select the glyph, one text bow each
		# to show the current left side bearing and right side bearing
		self.view_group = Group("auto")
		self.view_group.glyphView = GlyphView(
			"auto",
			layer=self.layer,
			backgroundColor=NSColor.clearColor()
		)
		self.view_group.glyphSelector = ComboBox(
			"auto",
			[glyph.name for glyph in self.glyphs],
			callback=self.glyph_selector_callback
		)
		self.view_group.glyphSelector.set(self.glyph_name)

		original_metrics = self.parent.original_metrics(self.glyph_name, self.master.id)

		self.view_group.originalLeftSideBearing = TextBox(
			"auto",
			"(%s)" % original_metrics[0],
			alignment="left"
		)
		self.view_group.originalRightSideBearing = TextBox(
			"auto",
			"(%s)" % original_metrics[1],
			alignment="right"
		)
		self.view_group.padding1 = Group("auto")
		self.view_group.padding2 = Group("auto")

		self.view_group.currentLeftSideBearing = TextBox(
			"auto",
			sidebearing(self.layer, "LSB"),
			alignment="left"
		)
		self.view_group.currentRightSideBearing = TextBox(
			"auto",
			sidebearing(self.layer, "RSB"),
			alignment="right"
		)

		self.glyphInfo = HTLSGlyphInfo(self.parent, glyph_name, self.glyphs, self.master)
		self.view_group.glyphInfo = self.glyphInfo.info_group

		# add rules to the glyph view groups
		view_group_rules = [
			"H:|-margin-[glyphView]-margin-|",
			"H:|-margin-[glyphSelector]-margin-|",
			"H:|-20-[originalLeftSideBearing]-margin-[originalRightSideBearing]-20-|",
			"H:|-20-[currentLeftSideBearing]-margin-[currentRightSideBearing]-20-|",
			"H:|-margin-[glyphInfo]-margin-|",
			"V:|-margin-[glyphView]-margin-[glyphSelector]-margin-[glyphInfo]-margin-|",
			"V:|-margin-[originalLeftSideBearing]",
			"V:|-margin-[originalRightSideBearing]",
			"V:|-[padding1]-[currentLeftSideBearing]-[padding2(==padding1)]-[glyphSelector]",
			"V:|-[padding1]-[currentRightSideBearing]-[padding2(==padding1)]-[glyphSelector]",
		]

		self.view_group.addAutoPosSizeRules(view_group_rules, self.parent.metrics)

	@guarded
	def glyph_selector_callback(self, sender):
		if sender.get() in self.glyphs:
			self.set_glyph(sender.get())

	def set_glyph(self, glyph_name):
		if glyph_name in self.glyphs:
			self.glyph = self.glyphs[glyph_name]
			self.glyph_name = self.glyph.name
		self.layer = self.glyph.layers[self.master.id]
		self.view_group.glyphView.layer = self.glyph.layers[self.parent.font.selectedFontMaster.id]
		self.view_group.glyphSelector.set(self.glyph_name)

		original_metrics = self.parent.original_metrics(self.glyph_name, self.master.id)
		self.view_group.originalLeftSideBearing.set("(%s)" % original_metrics[0])
		self.view_group.originalRightSideBearing.set("(%s)" % original_metrics[1])
		self.view_group.currentLeftSideBearing.set(sidebearing(self.layer, "LSB"))
		self.view_group.currentRightSideBearing.set(sidebearing(self.layer, "RSB"))

		# update case, category and subcategory
		self.view_group.glyphInfo.category.set("Category: %s" % self.glyph.category)
		self.view_group.glyphInfo.subCategory.set("Subcategory: %s" % self.glyph.subCategory)
		self.view_group.glyphInfo.case.set("Case: %s" % self.parent.case_name(self.glyph.case))

		self.glyphInfo.glyph = self.glyph
		self.glyphInfo.glyph_name = self.glyph_name
		self.glyphInfo.layer = self.layer
		self.glyphInfo.set_exception_settings()

	def update_layer(self, master):
		self.master = master
		self.layer = self.glyph.layers[self.master.id]
		self.view_group.glyphView.layer = self.layer
		original_metrics = self.parent.original_metrics(self.glyph_name, self.master.id)
		self.view_group.originalLeftSideBearing.set("(%s)" % original_metrics[0])
		self.view_group.originalRightSideBearing.set("(%s)" % original_metrics[1])

	def update_sidebearings(self, master):
		self.master = master
		self.layer = self.glyph.layers[self.master.id]
		self.view_group.currentLeftSideBearing.set(sidebearing(self.layer, "LSB"))
		self.view_group.currentRightSideBearing.set(sidebearing(self.layer, "RSB"))


class HTLSGlyphInfo:
	def __init__(self, parent, glyph_name, glyphs, master):
		if glyph_name not in glyphs:
			glyph_name = glyphs[0].name
		self.parent = parent
		self.glyphs = glyphs
		self.glyph = glyphs[glyph_name]
		self.glyph_name = self.glyph.name
		self.master = master
		self.layer = self.glyph.layers[master.id]

		self.info_group = Group("auto")
		self.info_group.category = TextBox(
			"auto",
			"Category: %s" % self.glyph.category,
			sizeStyle="small"
		)
		self.info_group.subCategory = TextBox(
			"auto",
			"Subcategory: %s" % self.glyph.subCategory,
			sizeStyle="small"
		)
		self.info_group.case = TextBox(
			"auto",
			"Case: %s" % self.parent.case_name(self.glyph.case),
			sizeStyle="small"
		)
		self.info_group.referenceGlyph = TextBox(
			"auto",
			"Reference glyph: None",
			sizeStyle="small"
		)
		self.info_group.factor = TextBox(
			"auto",
			"Factor: 1.0",
			sizeStyle="small"
		)

		self.set_exception_settings()

		info_rules = [
			"H:|-margin-[category]",
			"H:|-margin-[subCategory]",
			"H:|-margin-[case]",
			"H:|-margin-[referenceGlyph]",
			"H:|-margin-[factor]",
			"V:|-margin-[category]-[subCategory]-[case]-[referenceGlyph]-[factor]|",
		]

		self.info_group.addAutoPosSizeRules(info_rules, self.parent.metrics)

	def set_exception_settings(self):
		self.info_group.category.set("Category: %s" % self.glyph.category)
		self.info_group.subCategory.set("Subcategory: %s" % self.glyph.subCategory)
		self.info_group.case.set("Case: %s" % self.parent.case_name(self.glyph.case))

		try:
			rule = HTLSEngine(self.layer).find_exception()
		except Exception:
			rule = None
			print("HTLS Manager: could not read the spacing rule\n%s" % traceback.format_exc())

		if rule:
			self.info_group.referenceGlyph.set("Reference Glyph: %s" % rule.get("referenceGlyph"))
			try:
				factor = float(rule.get("value"))
			except (TypeError, ValueError):
				factor = 1.0
			self.info_group.factor.set("Factor: %s" % factor)
		else:
			self.info_group.referenceGlyph.set("Reference glyph: None")
			self.info_group.factor.set("Factor: 1.0")


class HTLSParameterSlider:
	def __init__(self, parent, parameter, master_id, current_value, min_value, max_value):
		self.parent = parent
		self.parameter = parameter
		self.master_id = master_id
		self.current_value = current_value
		self.min_value = min_value
		self.max_value = max_value

		# add a group with the following elements: a Slider, a TextBox to show the current value of the parameter
		# to show the current left side bearing and right side bearing
		self.slider_group = Group("auto")
		self.slider_group.title = TextBox("auto", self.title())
		self.slider_group.slider = Slider(
			"auto",
			minValue=self.min_value,
			maxValue=self.max_value,
			callback=self.enter_parameter_callback
		)
		self.slider_group.field = EditText(
			"auto",
			text=text(self.current_value),
			continuous=False,
			callback=self.enter_parameter_callback
		)

		self.slider_group.slider.set(self.current_value)

		# add rules to the slider group
		slider_group_rules = [
			"H:|-margin-[title(70)]-margin-[slider]-margin-[field(50)]-margin-|",
			"V:|[slider]-margin-|",
			"V:|[title]",
			"V:|[field]",
		]

		self.parent.master_parameters_sliders[self.parameter] = self.slider_group.slider
		self.parent.master_parameters_fields[self.parameter] = self.slider_group.field

		self.slider_group.addAutoPosSizeRules(slider_group_rules, parent.metrics)

	def title(self):
		return "%s (%s)" % (
			self.parameter.replace("param", "").title(),
			self.parent.parameters_for_master(self.master_id)[self.parameter]
		)

	@guarded
	def enter_parameter_callback(self, sender):
		# if the sender is the slider, update the value text field
		if sender == self.parent.master_parameters_sliders[self.parameter]:
			self.parent.master_parameters_fields[self.parameter].set(text(int(sender.get())))
		# if the sender is the value text field, update the slider
		elif sender == self.parent.master_parameters_fields[self.parameter]:
			if not text(sender.get()).strip().isnumeric():
				Message(title="Value must be a number", message="Please only enter whole number values.", )
				return
			self.parent.master_parameters_sliders[self.parameter].set(int(sender.get()))

		value = int(sender.get())
		self.parent.set_master_parameter(self.master_id, self.parameter, value)
		self.parent.apply_parameters_to_selection()
		self.parent.toggle_reset_parameters_button()
		self.parent.reset_area_slider_position(value)
		self.current_value = float(value)

	def reset_slider_position(self, value):
		if value == self.current_value:  # check whether slider was released
			self.min_value = int(self.current_value) - 100
			self.max_value = int(self.current_value) + 100
			self.slider_group.slider.set(int(self.current_value))
			self.slider_group.slider.setMinValue(self.min_value)
			self.slider_group.slider.setMaxValue(self.max_value)

	def ui_update(self, master_id, current_value, min_value=0, max_value=20):
		self.master_id = master_id
		self.current_value = current_value
		self.slider_group.slider.setMinValue(min_value)
		self.slider_group.slider.setMaxValue(max_value)
		self.slider_group.slider.set(current_value)
		self.slider_group.field.set(text(current_value))
		self.slider_group.title.set(self.title())


class HTLSFontRuleGroup:
	def __init__(self, parent, font_rules, category, rule_id):
		self.font_rules = font_rules
		self.parent = parent
		self.category = category
		self.rule_id = rule_id
		self.rule_group = None

		if self.rule_id not in self.font_rules[self.category]:
			return

		self.current_rule = self.font_rules[self.category][self.rule_id]

		self.sub_category = self.current_rule.get("subcategory") or "Any"
		self.case = self.current_rule.get("case") or 0
		self.filter = self.current_rule.get("filter") or ""
		self.reference_glyph = self.current_rule.get("referenceGlyph") or ""
		try:
			self.factor = str(round(float(self.current_rule.get("value")), 2)).replace(",", ".")
		except (TypeError, ValueError):
			self.factor = "1"

		# the subcategory list has to contain the rule's subcategory, or the popup cannot show it
		if self.sub_category not in parent.sub_categories[self.category]:
			parent.sub_categories[self.category].append(self.sub_category)
		if self.reference_glyph and self.reference_glyph not in parent.font.glyphs:
			self.reference_glyph = "(Invalid)"

		self.rule_group = Group("auto")
		self.rule_group.subcategory = PopUpButton(
			"auto",
			self.parent.sub_categories[self.category],
			callback=self.parent.update_font_rule
		)
		self.rule_group.case = PopUpButton(
			"auto",
			self.parent.cases,
			callback=self.parent.update_font_rule
		)
		self.rule_group.value = EditText(
			"auto",
			continuous=False,
			text=self.factor,
			callback=self.parent.update_font_rule
		)
		self.rule_group.filter = EditText(
			"auto",
			continuous=False,
			placeholder="None",
			text=self.filter,
			callback=self.parent.update_font_rule
		)
		self.rule_group.removeButton = Button(
			"auto",
			"Remove rule",
			callback=self.parent.remove_font_rule_callback
		)
		self.rule_group.referenceGlyph = ComboBox(
			"auto",
			[glyph.name for glyph in self.parent.font.glyphs],
			callback=self.parent.update_font_rule
		)

		self.rule_group.subcategory.setItem(self.sub_category)
		self.rule_group.case.set(self.case)
		self.rule_group.referenceGlyph.set(self.reference_glyph)

		group_rules = [
			"H:|-margin-[subcategory(116)]-margin-[case]-margin-[filter(==value)]-margin-[referenceGlyph(90)]-margin-"
			"[value(60)]-margin-[removeButton]|",
			"V:|[value(22)]|",
			"V:|[subcategory(==value)]|",
			"V:|[case(==value)]|",
			"V:|[referenceGlyph(==value)]|",
			"V:|[filter(==value)]|",
			"V:|[removeButton(==value)]|",
		]

		self.rule_group.addAutoPosSizeRules(group_rules, self.parent.metrics)

		# add all group elements to the elements set
		self.parent.font_rules_elements.add(self.rule_group.subcategory)
		self.parent.font_rules_elements.add(self.rule_group.case)
		self.parent.font_rules_elements.add(self.rule_group.value)
		self.parent.font_rules_elements.add(self.rule_group.referenceGlyph)
		self.parent.font_rules_elements.add(self.rule_group.filter)
		self.parent.font_rules_elements.add(self.rule_group.removeButton)

		# add the group to the rule group dictionary with ID
		self.parent.font_rules_groups[self.rule_id] = self.rule_group


class HTLSMasterRuleGroup:
	def __init__(self, parent, font_rules, category, rule):
		self.font_rules = font_rules
		self.parent = parent
		self.category = category
		self.rule = rule
		self.rule_group = None

		if rule not in self.font_rules[self.category] or len(self.font_rules[self.category][self.rule]) == 0:
			return

		self.current_rule = self.font_rules[self.category][self.rule]
		try:
			placeholder = str(round(float(self.current_rule.get("value")), 2)).replace(",", ".")
		except (TypeError, ValueError):
			placeholder = "1"

		self.rule_group = Group("auto")
		self.rule_group.subcategory = TextBox("auto", text(self.current_rule.get("subcategory") or "Any"))
		self.rule_group.case = TextBox("auto", self.parent.case_name(self.current_rule.get("case")))
		self.rule_group.filter = TextBox("auto", text(self.current_rule.get("filter") or "Any"))
		self.rule_group.value = EditText(
			"auto",
			continuous=False,
			text="",
			placeholder=placeholder,
			callback=self.parent.update_master_rule
		)
		self.rule_group.resetButton = Button("auto", "Reset", callback=self.parent.reset_master_rule)
		self.rule_group.resetButton.enable(False)

		# check if a value is stored in the master's user data for the current rule, if yes, use it
		master_rules = self.parent.font.selectedFontMaster.userData["HTLSManagerMasterRules"]
		if master_rules:
			if self.rule in master_rules:
				self.rule_group.value.set(text(master_rules[self.rule]).replace(",", "."))
				self.rule_group.resetButton.enable(True)

		group_rules = [
			"H:|-margin-[subcategory(90)]-margin-[case(==subcategory)]-margin-[filter(==subcategory)]-margin-"
			"[value(==subcategory)]-margin-[resetButton]|",
			"V:|[value(22)]|",
			"V:|[subcategory(==value)]|",
			"V:|[case(==value)]|",
			"V:|[filter(==value)]|",
			"V:|[resetButton(==value)]|",
		]

		self.rule_group.addAutoPosSizeRules(group_rules, self.parent.metrics)

		# add all group elements to the elements set
		self.parent.master_rules_elements.add(self.rule_group.subcategory)
		self.parent.master_rules_elements.add(self.rule_group.case)
		self.parent.master_rules_elements.add(self.rule_group.value)
		self.parent.master_rules_elements.add(self.rule_group.filter)
		self.parent.master_rules_elements.add(self.rule_group.resetButton)

		# add the group to the rule group dictionary with ID
		self.parent.master_rules_groups[self.rule] = self.rule_group
