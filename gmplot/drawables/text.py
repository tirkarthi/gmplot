from gmplot.utility import _COLOR_ICON_PATH, _format_LatLng, _get_embeddable_image

class _Text(object):    
    def __init__(self, lat, lng, text, precision, **kwargs):
        '''
        Args:
            lat (float): Latitude of the text label.
            lng (float): Longitude of the text label.
            text (str): Text to display.
            precision (int): Number of digits after the decimal to round to for lat/lng values.

        Optional:

        Args:
            color (str): Text hex color.
        '''
        self._position = _format_LatLng(lat, lng, precision)
        self._text = text
        self._color = kwargs.get('color')
        self._icon = _get_embeddable_image(_COLOR_ICON_PATH % 'clear')

    def write(self, w):
        '''
        Write the text.

        Args:
            w (_Writer): Writer used to write the text.
        '''
        w.write('new google.maps.Marker({')
        w.indent()
        w.write('label: {')
        w.indent()
        w.write('text: "%s",' % self._text)
        if self._color is not None: w.write('color: "%s",' % self._color)
        w.write('fontWeight: "bold"')
        w.dedent()
        w.write('},')
        w.write('icon: "%s",' % self._icon)
        w.write('position: %s,' % self._position)
        w.write('map: map')
        w.dedent()
        w.write('});')
        w.write()
