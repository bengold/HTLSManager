# HT Letterspacer, an auto-spacing tool
# Copyright (C) 2009 - 2018, The HT Letterspacer Project Authors
# Version 1.11
from __future__ import division, print_function, unicode_literals

# program dependencies
from GlyphsApp import Glyphs, Message
import math
import traceback
from Foundation import NSMinX, NSMaxX, NSMinY, NSMaxY, NSMakePoint

paramFreq = 4


def master_parameter(master, parameter, default):
	"""Read an integer HTLS parameter off a master, falling back to a default."""
	try:
		value = master.customParameters[parameter]
	except Exception:
		return default
	try:
		return int(float(value))
	except (TypeError, ValueError):
		return default


def has_aligned_width(layer):
	try:
		return bool(layer.hasAlignedWidth())
	except Exception:
		return False


# point list area
def area(points):
	s = 0
	for ii in range(-1, len(points) - 1):
		s = s + (points[ii].x * points[ii + 1].y - points[ii + 1].x * points[ii].y)
	return abs(s) * 0.5


def intersections(layer, start_point, end_point):
	# the ObjC selector is not available in every Glyphs version, so fall back to the documented wrapper
	if hasattr(layer, "calculateIntersectionsStartPoint_endPoint_"):
		result = layer.calculateIntersectionsStartPoint_endPoint_(start_point, end_point)
	else:
		result = layer.intersectionsBetweenPoints(start_point, end_point)

	# depending on the version the intersections come back as NSValue or as plain points
	return [point.pointValue() if hasattr(point, "pointValue") else point for point in result]


# get margins in Glyphs
def get_margins(layer, y):
	start_point = NSMakePoint(NSMinX(layer.bounds) - 1, y)
	end_point = NSMakePoint(NSMaxX(layer.bounds) + 1, y)

	result = intersections(layer, start_point, end_point)
	count = len(result)
	if count <= 2:
		return None, None

	left = 1
	right = count - 2
	return result[left].x, result[right].x


def triangle(angle, y):
	angle = math.radians(angle)
	result = y * (math.tan(angle))
	# result = round(result)
	return result


def total_margin_list(layer, min_y, max_y, angle, min_y_ref, max_y_ref):
	# totalMarginList(layer,minY,maxY,angle,minYref,maxYref)
	# the list of margins
	y = min_y
	list_l = []
	list_r = []

	# calculate default depth, otherwise measurement is None
	# calculate paralelogram extremes
	origin = NSMinX(layer.bounds)
	endpointx = NSMaxX(layer.bounds)
	endpointy = NSMaxY(layer.bounds)

	# calculate paralelogram top left
	xpos = triangle(angle, endpointy) + origin
	# paralelogram top side width
	slant_width = (endpointx - xpos)
	# default depth
	dflt_depth = slant_width

	# result will be false if all the measured margins are emtpy (no outlines in reference zone)
	result = False

	while y <= max_y:
		lpos, rpos = get_margins(layer, y)

		# get the default margin measure at a given y position
		slant_pos_l = origin + triangle(angle, y) + dflt_depth
		slant_pos_r = origin + triangle(angle, y)

		if lpos is not None:
			list_l.append(NSMakePoint(lpos, y))
			if min_y_ref <= y <= max_y_ref:
				result = True
		else:
			list_l.append(NSMakePoint(slant_pos_l, y))

		if rpos is not None:
			list_r.append(NSMakePoint(rpos, y))
			if min_y_ref <= y <= max_y_ref:
				result = True
		else:
			list_r.append(NSMakePoint(slant_pos_r, y))

		y += paramFreq

	# if no measurements are taken, returns false and will abort in main function
	if result:
		return list_l, list_r
	else:
		return False, False


def zone_margins(l_margins, r_margins, min_y, max_y):
	# filter those outside the range
	points_filtered_l = [x for x in l_margins if min_y <= x.y <= max_y]
	points_filtered_r = [x for x in r_margins if min_y <= x.y <= max_y]

	return points_filtered_l, points_filtered_r


def max_points(points):
	# this function returns the extremes for a given set of points in a given zone

	# filter those outside the range
	# pointsFilteredL = [ x for x in points[0] if x.y>=minY and x.y<=maxY]
	# pointsFilteredR = [ x for x in points[0] if x.y>=minY and x.y<=maxY]

	# without any measurements there are no extremes to report
	if not points[0] or not points[1]:
		return None, None

	# sort all given points by x
	sort_points_by_xl = sorted(points[0], key=lambda tup: tup[0])
	sort_points_by_xr = sorted(points[1], key=lambda tup: tup[0])

	# get the extremes position, first and last in the list
	left, lefty = sort_points_by_xl[0]
	right, righty = sort_points_by_xr[-1]

	return NSMakePoint(left, lefty), NSMakePoint(right, righty)


def diagonize(margins_l, margins_r):
	if len(margins_l) < 2 or len(margins_r) < 2:
		return margins_l, margins_r
	ystep = abs(margins_l[0].y - margins_l[1].y)
	for i in range(len(margins_l) - 1):
		if margins_l[i + 1].x - margins_l[i].x > ystep:
			margins_l[i + 1].x = margins_l[i].x + ystep
		if margins_r[i + 1].x - margins_r[i].x < -ystep:
			margins_r[i + 1].x = margins_r[i].x - ystep

	for i in reversed(range(len(margins_l) - 1)):
		if margins_l[i].x - margins_l[i + 1].x > ystep:
			margins_l[i].x = margins_l[i + 1].x + ystep
		if margins_r[i].x - margins_r[i + 1].x < -ystep:
			margins_r[i].x = margins_r[i + 1].x - ystep

	return margins_l, margins_r


def read_config(font):
	categories = ["Letter", "Number", "Punctuation", "Symbol", "Mark"]

	font_rules = {}

	try:
		nsdict_fontrules = font.userData["com.eweracs.HTLSManager.fontRules"]
	except Exception:
		nsdict_fontrules = None
	if nsdict_fontrules:
		for category in nsdict_fontrules:
			font_rules[category] = {}
			for rule_id in nsdict_fontrules[category]:
				try:
					font_rules[category][rule_id] = dict(nsdict_fontrules[category][rule_id])
				except (TypeError, ValueError):
					continue

	# if the category is not in the dictionary, add it
	for category in categories:
		if category not in font_rules:
			font_rules[category] = {}

	return font_rules


class HTLSEngine:

	def __init__(self, layer, parent=None):
		self.categories = ["Letter", "Number", "Punctuation", "Symbol", "Mark"]
		self.parent = parent
		self.layer = layer

		# every attribute is set up front: an engine built on an unusable layer stays inert instead of
		# raising an AttributeError further down
		self.valid = False
		self.font = None
		self.master = None
		self.glyph = None
		self.reference_layer = layer
		self.minYref = None
		self.maxYref = None
		self.minY = None
		self.maxY = None
		self.newR = None
		self.newL = None
		self.distance_l = 0
		self.distance_r = 0
		self.tabular_width = False
		self.skip_LSB = False
		self.skip_RSB = False
		self.xHeight = 0
		self.angle = 0
		self.upm = 1000
		self.factor = 1
		self.rule = None
		self.master_rules = None
		self.l_polygon = None
		self.r_polygon = None
		self.config = {category: {} for category in self.categories}
		self.output = ""

		if layer is None:
			return

		self.glyph = layer.parent
		if self.glyph is None or not self.glyph.name:
			return

		self.font = self.glyph.parent
		if self.font is None:
			return

		try:
			self.master = layer.master or self.font.masters[layer.associatedMasterId]
		except Exception:
			self.master = None
		if self.master is None:
			return

		self.xHeight = int(self.master.xHeight)
		self.angle = layer.italicAngle or 0
		self.upm = int(self.font.upm)
		self.output = "Spacing...\nLayer: %s (%s)\n" % (self.glyph.name, self.master.name)

		self.config = read_config(self.font)
		self.master_rules = self.master.userData["HTLSManagerMasterRules"]

		# the engine runs once per layer, so a bad parameter must not put up a modal alert
		self.paramArea = master_parameter(self.master, "paramArea", 400)
		self.paramDepth = master_parameter(self.master, "paramDepth", 12)
		self.paramOver = 0  # self.master.customParameters["paramOver"] or 0
		self.paramFreq = 4  # self.master.customParameters["paramFreq"] or 4

		self.valid = True

		if ".tosf" in self.glyph.name or ".tf" in self.glyph.name \
			or self.glyph.widthMetricsKey or self.layer.widthMetricsKey \
			or self.font.customParameters["isFixedPitch"]:
			self.tabular_width = True
			self.output += "Using fixed width: %s.\n" % int(self.layer.width)

		self.rule = self.find_exception()
		if self.rule:
			try:
				self.factor = float(self.rule["value"])
			except (TypeError, ValueError):
				self.factor = 1
			reference_name = self.rule.get("referenceGlyph")
			reference_glyph = self.font.glyphs[reference_name] if reference_name else None
			if reference_glyph:
				reference_layer = reference_glyph.layers[self.layer.associatedMasterId]
				if reference_layer is not None:
					self.reference_layer = reference_layer

		self.output += "Reference: %s\nFactor: %s" % (self.reference_layer.parent.name, float(self.factor))

		if parent:
			try:
				if self.parent.leftGlyphView.glyph_name == self.glyph.name:
					self.parent.parametersTab.leftGlyphView.glyphInfo.factor.set("Factor: %s" % self.factor)
				if self.parent.rightGlyphView.glyph_name == self.glyph.name:
					self.parent.parametersTab.rightGlyphView.glyphInfo.factor.set("Factor: %s" % self.factor)
			except Exception:
				print("HT Letterspacer: could not update the factor display\n%s" % traceback.format_exc())

	def find_exception(self):
		if not self.valid:
			return None

		glyph = self.glyph
		name = glyph.name
		category = glyph.category
		subcategory = glyph.subCategory
		case = glyph.case

		if category not in self.categories:
			return

		rule = None
		rule_id = None

		# highly un-dynamic best rule determination incoming pog

		for id in self.config[category]:
			rule_subcategory = self.config[category][id].get("subcategory")
			rule_case = self.config[category][id].get("case")
			rule_filter = self.config[category][id].get("filter") or None

			# check for rules with defined subcategory, defined case and defined filter
			if subcategory == rule_subcategory:
				if case == rule_case:
					if rule_filter and rule_filter in name:
						rule = dict(self.config[category][id])
						rule_id = id
						break

		if not rule:
			for id in self.config[category]:
				rule_subcategory = self.config[category][id].get("subcategory")
				rule_case = self.config[category][id].get("case")
				rule_filter = self.config[category][id].get("filter") or None

				# check for rules with defined subcategory, defined case and no filter
				if subcategory == rule_subcategory:
					if case == rule_case:
						if not rule_filter:
							rule = dict(self.config[category][id])
							rule_id = id
							break

		if not rule:
			for id in self.config[category]:
				rule_subcategory = self.config[category][id].get("subcategory")
				rule_case = self.config[category][id].get("case")
				rule_filter = self.config[category][id].get("filter") or None

				# check for rules with undefined subcategory, defined case and defined filter
				if rule_subcategory == "Any":
					if case == rule_case:
						if rule_filter and rule_filter in name:
							rule = dict(self.config[category][id])
							rule_id = id
							break

		if not rule:
			for id in self.config[category]:
				rule_subcategory = self.config[category][id].get("subcategory")
				rule_case = self.config[category][id].get("case")
				rule_filter = self.config[category][id].get("filter") or None

				# check for rules with undefined subcategory, defined case and no filter
				if rule_subcategory == "Any":
					if case == rule_case:
						if not rule_filter:
							rule = dict(self.config[category][id])
							rule_id = id
							break

		if not rule:
			for id in self.config[category]:
				rule_subcategory = self.config[category][id].get("subcategory")
				rule_case = self.config[category][id].get("case")
				rule_filter = self.config[category][id].get("filter") or None

				# check for rules with undefined subcategory, undefined case and defined filter
				if rule_subcategory == "Any":
					if rule_case in (0, "Any"):
						if rule_filter and rule_filter in name:
							rule = dict(self.config[category][id])
							rule_id = id
							break

		if not rule:
			for id in self.config[category]:
				rule_subcategory = self.config[category][id].get("subcategory")
				rule_case = self.config[category][id].get("case")
				rule_filter = self.config[category][id].get("filter") or None

				# check for rules with undefined subcategory, undefined case and no filter
				if rule_subcategory == "Any":
					if rule_case in (0, "Any"):
						if not rule_filter:
							rule = dict(self.config[category][id])
							rule_id = id
							break

		if rule_id and self.master_rules and rule_id in self.master_rules:
			rule["value"] = self.master_rules[rule_id]

		if rule:
			self.output += "Found spacing rule.\n"
		else:
			self.output += "No spacing rule found.\n"

		return rule

	def overshoot(self):
		return self.xHeight * self.paramOver / 100

	def process_margins(self, l_margin, r_margin, l_extreme, r_extreme):
		# set depth
		l_margin, r_margin = self.set_depth(l_margin, r_margin, l_extreme, r_extreme)

		# close open counterforms at 45 degrees
		l_margin, r_margin = diagonize(l_margin, r_margin)
		l_margin = self.close_open_counters(l_margin, l_extreme)
		r_margin = self.close_open_counters(r_margin, r_extreme)

		return l_margin, r_margin

	# process lists with depth, proportional to xheight
	def set_depth(self, margins_l, margins_r, l_extreme, r_extreme):
		if not margins_l or not margins_r:
			return margins_l, margins_r

		depth = self.xHeight * self.paramDepth / 100
		maxdepth = l_extreme.x + depth
		mindepth = r_extreme.x - depth
		margins_l = [NSMakePoint(min(p.x, maxdepth), p.y) for p in margins_l]
		margins_r = [NSMakePoint(max(p.x, mindepth), p.y) for p in margins_r]

		# add all the points at maximum depth if glyph is shorter than overshoot
		y = margins_l[0].y - self.paramFreq
		while y > self.minYref:
			margins_l.insert(0, NSMakePoint(maxdepth, y))
			margins_r.insert(0, NSMakePoint(mindepth, y))
			y -= self.paramFreq

		y = margins_l[-1].y + self.paramFreq
		while y < self.maxYref:
			margins_l.append(NSMakePoint(maxdepth, y))
			margins_r.append(NSMakePoint(mindepth, y))
			y += self.paramFreq

		return margins_l, margins_r

	# close counterforms, creating a polygon
	def close_open_counters(self, margin, extreme):
		init_point = NSMakePoint(extreme.x, self.minYref)
		end_point = NSMakePoint(extreme.x, self.maxYref)
		margin.insert(0, init_point)
		margin.append(end_point)
		return margin

	def deslant(self, margin):
		"""De-slant a list of points (contour) at angle with the point of origin
		at half the xheight."""
		mline = self.xHeight / 2
		return [
			NSMakePoint(p.x - (p.y - mline) * math.tan(math.radians(self.angle)), p.y)
			for p in margin
		]

	def calculate_sb_value(self, polygon):
		amplitude_y = self.maxYref - self.minYref
		# a zero reference zone or a master without an x-height would divide by zero
		if not amplitude_y or not self.xHeight:
			return None

		# recalculates area based on UPM
		area_upm = self.paramArea * ((self.upm / 1000) ** 2)
		# calculates proportional area
		white_area = area_upm * self.factor * 100

		prop_area = (amplitude_y * white_area) / self.xHeight

		valor = prop_area - area(polygon)
		return valor / amplitude_y

	def calculate_polygons(self):
		if not self.valid:
			return
		elif not self.layer.name or len(self.layer.components) + len(self.layer.paths) == 0:
			return
		elif has_aligned_width(self.layer):
			self.output = "Glyph %s has aligned width. Skipping.\n__________________\n" % self.glyph.name
			return
		elif self.glyph.leftMetricsKey:
			self.skip_LSB = True
			self.output += "Glyph %s has left metrics key." % self.glyph.name
		elif self.glyph.rightMetricsKey:
			self.skip_RSB = True
			self.output += "Glyph %s has right metrics key." % self.glyph.name
		elif "fraction" in self.glyph.name:
			self.output = "Glyph fraction should be spaced manually. Skipping.\n__________________\n"
			return

		self.output += "\n__________________\n"
		# Decompose layer for analysis, as the deeper plumbing assumes to be looking at outlines.
		try:
			layer_decomposed = self.layer.copyDecomposedLayer()
			layer_decomposed.parent = self.glyph
		except Exception:
			self.output += "Could not decompose the layer. Skipping.\n%s\n" % traceback.format_exc()
			return
		# get reference glyph maximum points
		overshoot = self.overshoot()

		# store min and max y
		self.minYref = NSMinY(self.reference_layer.bounds) - overshoot
		self.maxYref = NSMaxY(self.reference_layer.bounds) + overshoot

		self.minY = NSMinY(layer_decomposed.bounds)
		self.maxY = NSMaxY(layer_decomposed.bounds)

		# get the margins for the full outline
		# will take measure from minY to maxY. minYref and maxYref are passed to check reference match
		# totalMarginList(layer,minY,maxY,angle,minYref,maxYref)
		l_total_margins, r_total_margins = total_margin_list(
			layer_decomposed,
			self.minY,
			self.maxY,
			self.angle,
			self.minYref,
			self.maxYref
		)

		# margins will be False, False if there is no measure in the reference zone, and then function stops
		if not l_total_margins and not r_total_margins:
			return

		# filtes all the margins to the reference zone
		l_zone_margins, r_zone_margins = zone_margins(l_total_margins, r_total_margins, self.minYref, self.maxYref)

		# if the font has an angle, we need to deslant
		if self.angle:
			l_zone_margins = self.deslant(l_zone_margins)
			r_zone_margins = self.deslant(r_zone_margins)

			l_total_margins = self.deslant(l_total_margins)
			r_total_margins = self.deslant(r_total_margins)

		# full shape extreme points
		self.l_full_extreme, self.r_full_extreme = max_points([l_total_margins, r_total_margins])
		# get zone extreme points
		l_extreme, r_extreme = max_points([l_zone_margins, r_zone_margins])

		if None in (self.l_full_extreme, self.r_full_extreme, l_extreme, r_extreme):
			self.output += "No outlines in the reference zone. Skipping.\n"
			return

		# dif between extremes full and zone
		self.distance_l = math.ceil(l_extreme.x - self.l_full_extreme.x)
		self.distance_r = math.ceil(self.r_full_extreme.x - r_extreme.x)

		# create a closed polygon
		self.l_polygon, self.r_polygon = self.process_margins(l_zone_margins, r_zone_margins, l_extreme, r_extreme)

		return self.l_polygon, self.r_polygon

	def current_layer_sidebearings(self):
		if not self.calculate_polygons():
			return

		l_value = self.calculate_sb_value(self.l_polygon)
		r_value = self.calculate_sb_value(self.r_polygon)
		if l_value is None or r_value is None:
			return

		self.newL = math.ceil(0 - self.distance_l + l_value)
		self.newR = math.ceil(0 - self.distance_r + r_value)

		if self.tabular_width:
			width_shape = self.r_full_extreme.x - self.l_full_extreme.x
			width_actual = width_shape + self.newL + self.newR
			width_diff = (self.layer.width - width_actual) / 2

			self.newL += width_diff
			self.newR += width_diff

		else:
			if self.skip_LSB:
				self.newL = self.layer.LSB
			if self.skip_RSB:
				self.newR = self.layer.RSB

		return self.newL, self.newR


class HTLSScript:
	def __init__(self, all_masters):
		self.font = Glyphs.font

		if self.font is None:
			Message("No font selected", "Select a font project!")
			return

		master = self.font.selectedFontMaster
		if master is None:
			Message("Open the font in an Edit view first.", "No master selected")
			return

		if not master.customParameters["paramArea"] or not master.customParameters["paramDepth"]:
			Message(
				title="Missing configuration",
				message="Please set up parameters in HTLS Manager. Using default values."
			)

		for glyph in self.font.selectedLayers:
			parent = glyph.parent
			for layer in parent.layers:
				if not layer.isMasterLayer:
					continue
				if not all_masters and layer.associatedMasterId != master.id:
					continue
				self.engine = HTLSEngine(layer)

				layer_lsb, layer_rsb = self.engine.current_layer_sidebearings() or [None, None]
				if layer_lsb is None and layer_rsb is None:
					continue
				layer.LSB, layer.RSB = layer_lsb, layer_rsb
				layer.syncMetrics()

				print(self.engine.output)
