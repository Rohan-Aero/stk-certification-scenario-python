stk.v.9.0

BEGIN ReportStyle
Name		Ica_LatLon

BEGIN ClassId
	Class		Place
END ClassId

BEGIN Header
	StyleType		0
	Title		Ica_LatLon
	Date		Yes
	Name		Yes
	DescShort		No
	DescLong		No
	YLog10		No
	Y2Log10		No
	Ticks		No
	GridLines		No
	NumAnnotations		3
	AnnotationRotation		1
	NumTick		12
	NumGridX		12
	NumGridY		12
	BackgroundColor		7
	ViewableDuration		0.000000

BEGIN PostProcessor
	Destination	0
	Use	0
	Destination	1
	Use	0
	Destination	2
	Use	0
	Destination	3
	Use	0
END PostProcessor
	NumSections		1
END Header

BEGIN Section
	Name		Section 1
	ClassName		Place
	NameInTitle		No
	ExpandMethod		0
	PropMask		1
	ShowIntervals		No
	NumIntervals		0
	NumLines		1

BEGIN Line
	Name		Line 1
	NumElements		2

BEGIN Element
	Name		LLA State-Lat
	IsIndepVar		No
	Title		Lat
	NameInTitle		No
	Service		LLAState
	Element		Lat
	SumAllowedMask		0
	SummaryOnly		No
	DataType		0
	UnitType		19
	LineStyle		0
	LineWidth		0
	LineColor		0
	PointStyle		0
	PointSize		0
	PointColor		0
	FillPattern		0
	FillColor		0
	UseScenUnits		Yes
END Element

BEGIN Element
	Name		LLA State-Lon
	IsIndepVar		No
	Title		Lon
	NameInTitle		No
	Service		LLAState
	Element		Lon
	SumAllowedMask		0
	SummaryOnly		No
	DataType		0
	UnitType		20
	LineStyle		0
	LineWidth		0
	LineColor		0
	PointStyle		0
	PointSize		0
	PointColor		0
	FillPattern		0
	FillColor		0
	UseScenUnits		Yes
END Element

END Line
END Section
END ReportStyle

