### Encoding: utf-8 (needed for Python 2)

import sys
import os
import shutil
import inspect
import warnings
import base64
import re

from gmplot.color import _get_hex_color

_INDENT_LEVEL = 4
_INDENT = ' ' * _INDENT_LEVEL
# Note: This should match a single indent used in the actual source code.

_COLOR_ICON_PATH = os.path.join(os.path.dirname(__file__), 'markers/%s.png')

if sys.version_info.major == 2:
    from StringIO import StringIO as _StringIO

    class StringIO(_StringIO):
        def __enter__(self):
            return self

        def __exit__(self, exception_type, exception_value, traceback):
            '''
            Args:
                exception_type: Type of exception that triggered the exit. 
                exception_value: Value of exception that triggered the exit.
                traceback: Traceback when exit was triggered.
            '''
            self.close()

else:
    from io import StringIO # pragma: no coverage

def _get_value(dict, keys, default=None, get_key=False):
    '''
    Get the value of any of the provided keys.

    Note: Only use `dict.get()` if you have a single key and no optional parameters set,
          otherwise, prefer this function.

    Args:
        dict (dict): Dict to obtain the value from.
        keys ([str]): Keys of interest, in order of preference.

    Optional:
    
    Args:
        default: Value to return if none of the keys have a value. Defaults to None.
        get_key (bool): Whether or not to also return the key associated with the returned value. Defaults to False.

    Returns:
        any or (str, any): Value of the first valid key, or a tuple of the key and its value if ``get_key`` is True.
            If the default value is returned, the key is None.
    '''
    for key in keys:
        value = dict.get(key)
        if value is not None:
            return value if not get_key else (key, value)
    return default if not get_key else (None, default)

def _get_options(parameters, parameter_map):
    '''
    Get a collection of usable (formatted) options from the provided parameters and the associated parameter map.

    Args:
        parameters (dict): Parameter names and their values.
        parameter_map (dict): Parameter names and their associated tuple:
            [0] ([str]): Full list of parameter names that correspond to this parameter.
            [1] (str): (optional) Default value for this parameter.

    Example::

        parameters = {
            'c': 'orange',
            'label': 'Point of interest'
        }

        options = _get_options(parameters, {
            'color': (['color', 'c'], 'red'),
            'title': (['title'],),
            'label': (['label'],),
            'draggable': (['draggable'], False)
        })

        print(options)

    .. code-block::

        -> {
               'color': '#FFA500',
               'draggable': False,
               'label': 'Point of interest'
           }
    '''
    options = {}
    for name, info in parameter_map.items():
        value = _get_value(parameters, *info)
        if value is not None:
            options[name] = value

    for key, value in options.items():
        if 'color' in key:
            options[key] = _get_hex_color(options[key])

    if 'travel_mode' in options: options['travel_mode'] = options['travel_mode'].upper()

    return options

def _format_LatLng(lat, lng, precision):
    '''
    Format the given latitude/longitude location as a Google Maps LatLng object.

    Args:
        lat (float): Latitude.
        lng (float): Longitude.
        precision (int): Number of digits after the decimal to round to for lat/lng values.

    Returns:
        str: Formatted Google Maps LatLng object.
    '''
    return 'new google.maps.LatLng(%.*f, %.*f)' % (precision, lat, precision, lng)

def _get_embeddable_image(path):
    '''
    Get an image as an embeddable base64 image URL.

    Args:
        path (str): Image path.

    Returns:
        str: Base64 image URL that can be embedded in a file.
    '''
    with open(path, 'rb') as f:
        return 'data:image/png;base64,' + base64.b64encode(f.read()).decode()

def _get_fresh_path(relative_path):
    '''
    Delete the contents of a given relative path then get its absolute path.

    Args:
        relative_path (str): Relative path to be cleaned up and returned as an absolute path.

    Returns:
        str: Absolute path of the given relative path.
    '''
    path = os.path.abspath(relative_path)
    if os.path.exists(path):
        shutil.rmtree(path)
    os.mkdir(path)
    return path

def _write_to_sidebar(file, name, link=None, depth=0):
    '''
    Add an item to the GitHub Wiki _Sidebar file as a link.

    Args:
        file (handle): _Sidebar file.
        name (str): Readable name of the item to be added.

    Optional:

    Args:
        link (str): Link to the item of interest. If not specified, the item name will be used as the link.
        depth (int): Indentation level of the given item in the _Sidebar. Defaults to 0.
    '''
    link_content = name
    if link is not None and name != link:
        link_content += '|' + link
    formatted_link = '[[%s]]' % link_content

    if depth == 0:
        file.write(_bookend(formatted_link, '**') + '\n')
    else:
        file.write(_INDENT * (depth - 1) + '* ' + formatted_link)
        
    file.write('\n')

class _GenerateDocFiles(object):
    '''
    Functor that autogenerates Sphinx source files for each public object (with a docstring)
    under a given module. This also adds corresponding GitHub Wiki _Sidebar links for each
    generated file. 
    '''

    def __init__(self, module, doc_directory, sidebar_file):
        '''
        Args:
            module: Module to parse and autogenerate documentation for.
            doc_directory (str): Sphinx directory to create the source files in.
            sidebar_file (handle): GitHub Wiki _Sidebar file.
        '''
        self.module = module
        self.doc_directory = doc_directory
        self.source_ext = '.rst'
        self.sidebar_file = sidebar_file

    def __call__(self):
        '''
        Returns:
            str: The extension of the autogenerated Sphinx source files.
        '''
        self._recurse(self.module, [])
        return self.source_ext

    def _recurse(self, element, ancestry):
        '''
        Helper function that recurses through the module tree to autogenerate documentation.

        Args:
            element: Element to process.
            ancestry ([str]): Current ancestry of the element, as a list ordered from its
                highest ancestor to its immediate parent.
        '''
        for name, item in element.__dict__.items():
            # Skip private and non-public items:
            if name[0] == '_':
                continue

            # Get the bound form of the element's item, if applicable
            # (this ensures that the actual item's docstring is read below):
            if hasattr(item, '__get__'):
                item = item.__get__(element)

            # Skip items that don't have a docstring:
            if item.__doc__ is None:
                continue

            # Get this item's ancestry:
            new_ancestry = ancestry.copy()
            new_ancestry.append(name)
            full_name = '.'.join(new_ancestry)

            # Determine the proper Sphinx directive for the item:
            doc_type = None
            if inspect.isroutine(item): # TODO: Likely incomplete - this doesn't handle modules nor attributes, for example.
                doc_type = 'automethod'
            elif inspect.isclass(item):
                doc_type = 'autoclass'
            else:
                warnings.warn("`%s`'s type isn't supported in documentation (or it isn't implemented yet)." % full_name)
                continue

            # Generate the Sphinx source file for this item:
            with open('%s/%s%s' % (self.doc_directory, full_name, self.source_ext), 'w') as file:
                file.write(':orphan:\n\n')
                file.write('.. %s:: %s::%s\n' % (doc_type, self.module.__name__, full_name))

            # Add a link to this item in the _Sidebar file:
            _write_to_sidebar(self.sidebar_file, name, full_name, len(ancestry))

            # Continue parsing the module tree:
            self._recurse(item, new_ancestry)

def _bookend(string, fragment):
    '''
    Bookend a given string with the given fragment on both ends.

    Args:
        string (str): String to bookend.
        fragment (str): Fragment to bookend the string with.

    Returns:
        str: Bookended string.
    '''
    if not string:
        return ''

    if string.startswith(fragment) and string.endswith(fragment):
        return string

    return fragment + string + fragment

def _pretty_format_signature_header(signature_header):
    '''
    Pretty format a given Markdown signature header.

    Args:
        signature_header (str): Signature header to format.
    
    Returns:
        str: Formatted signature header.

    Given:
        '### class module.function(param1, param2=None)'
    
    Output:
        '_class_ module.**function**(_param1, param2=None_)'
    '''
    new_header = ''

    # Trim the closing parenthesis:
    if signature_header[-1] != ')':
        return None
    signature_header = signature_header[:-1]

    # Split the parameters from the rest of the signature header:
    parenthesis_index = signature_header.find('(')
    if parenthesis_index == -1:
        return None

    parameters = _bookend(signature_header[parenthesis_index + 1:], '_')
    signature_header = signature_header[:parenthesis_index]
 
    # Split the rest of the signature header by whitespace:
    header_sections = signature_header.split()

    # Ensure the first portion of the header is a valid header level (e.g. '#' or '####'):
    header_level = header_sections[0]
    HEADER_CHARACTER = '#'
    if header_level[0] != HEADER_CHARACTER or header_level != len(header_level) * header_level[0]:
        return None

    # Get the annotation and full name portions of the header:
    if len(header_sections) == 2:
        annotation = None
        full_name = header_sections[1]
    elif len(header_sections) == 3:
        annotation = header_sections[1]
        full_name = header_sections[2]
    else:
        return None

    # If an annotation exists (e.g. 'class' or 'method'), add it to the new header,
    # and italicize it if needed:
    if annotation:
        new_header += _bookend(annotation, '_') + ' '

    # Split the scope from the name:
    last_period_index = full_name.rfind('.')
    if last_period_index == -1:
        return None

    scope = full_name[:last_period_index]
    name = _bookend(full_name[last_period_index + 1:], '**')

    # Rebuild the signature using the new format:
    new_header += scope + '.' + name + '(' + parameters + ')'

    return new_header

def _strip_character(string, character):
    '''
    Strip a character from a string without removing escaped characters.

    Args:
        string (str): String to process.
        character (str): Character to strip from the string.

    Returns:
        str: String with the character stripped.
    '''
    if character == '':
        return string

    escaped_character = '\\' + character
    return escaped_character.join([fragment.replace(character, '') for fragment in string.split(escaped_character)])

def _pretty_format_markdown(directory):
    '''
    Pretty format all Markdown files in the given directory.

    Args:
        directory (str): Directory containing the Markdown files to format. 
    '''
    _CODE_LITERAL_CHARACTER = '`'

    for filename in os.listdir(directory):

        # Skip non-Markdown files:
        if not filename.endswith(".md"):
            continue

        # Read the file's contents:
        with open(directory + filename, mode='r', encoding='utf-8') as file:
            lines = file.readlines()

        # Skip if there's no content:
        if not lines:
            continue

        # Pretty format the signature header:
        lines[0] = _pretty_format_signature_header(lines[0][:-1]) # (exclude trailing newline)
        if lines[0] is None:
            warnings.warn("Couldn't parse `%s`'s signature header." % filename)
            continue
        lines[0] += '\n'

        # Add a line break right after the header:
        lines.insert(1, '\n')
        lines.insert(2, '---\n')
        lines.insert(3, '\n')

        # Fuse the "Optional" header (if any) with the subsequent "Parameters" header:
        while True:
            index_optional = None
            index_parameters = None
            for index, line in enumerate(lines):
                if index_optional is not None:
                    if line == '* **Parameters**\n': 
                        index_parameters = index
                        break
                    elif line != '\n':
                        warnings.warn("Unexpected content after 'Optional' header!")
                        break
                elif line == 'Optional:\n':
                    index_optional = index

            if index_optional is not None and index_parameters is not None:
                lines[index_optional] = '* **Optional Parameters**\n'
                del lines[index_optional + 1 : index_parameters + 1]
            else:
                break # (don't do another pass if there are no more 'Optional/Parameters' pairs)
            
        # For each parameter line...
        _PARAMETER_REGEX = '(%s)(%s)(%s)' % (
            ' *.*? ', # Matches whatever comes before the type, like: '''  * **origin** '''
            '\(.*\)', # Matches whatever makes up the type, like:     '''(*(**float**, **float**)*)'''
            ' – .*'   # Matches whatever comes after the type, like:  ''' – Origin, in latitude/longitude.'''
        )

        for index, line in enumerate(lines):
            match = re.match(_PARAMETER_REGEX, line, flags=re.DOTALL)
            if match:
                sections = list(match.groups())

                # ...strip away the surrounding parentheses:
                sections[1] = sections[1][1:-1]

                # ...strip away all non-escaped asterisks:
                sections[1] = _strip_character(sections[1], '*')

                # ...format every type without touching any 'or' delimiters:
                _OR_DELIMITER = ' or ' 
                sections[1] = _OR_DELIMITER.join([_bookend(type_, _CODE_LITERAL_CHARACTER) for type_ in sections[1].split(_OR_DELIMITER)])

                lines[index] = ''.join(sections)

        # Merge the 'Return type' content (if any) with the'Returns' content (if any):
        index_returns_header = None
        index_return_type_header = None
        for index, line in enumerate(lines):
            if line == '* **Returns**\n':
                index_returns_header = index
            elif line == '* **Return type**\n':
                index_return_type_header = index

        if index_return_type_header is not None:
            assert index_returns_header is not None, "'Returns' header must exist if 'Return type' header exists."

            # Get the index of the 'Returns' content:
            index_returns_content = None
            start_index = index_returns_header + 1
            for index, line in enumerate(lines[start_index:]):
                if line == '* **Return type**\n':
                    break # (if the 'Return type' header is reached, then there is no 'Returns' content)
                elif not line.isspace():
                    index_returns_content = start_index + index
                    break

            # Get the index of the 'Return type' content (which is guaranteed to exist):
            index_return_type_content = None
            start_index = index_return_type_header + 1
            for index, line in enumerate(lines[start_index:]):
                if not line.isspace():
                    index_return_type_content = start_index + index
                    break

            _LINE_REGEX = '( *)(.*)(\n)'

            # If there actually is 'Returns' content...
            if index_returns_content is not None:

                # ...get the return type from the 'Return type' section:
                match = re.match(_LINE_REGEX, lines[index_return_type_content], flags=re.DOTALL)
                assert match, "'Return type' header must have some content below it."
                return_type = match.groups()[1]

                # ...delete the 'Return type' header and the content that comes below it:
                del lines[index_return_type_header : index_return_type_content + 1]

                # ...prepend the return type to the 'Return' content.
                match = re.match(_LINE_REGEX, lines[index_returns_content], flags=re.DOTALL)
                assert match, "'Return' header must have some content below it."
                sections = list(match.groups())
                sections[1] = _bookend(return_type, _CODE_LITERAL_CHARACTER) + ' – ' + sections[1]
                lines[index_returns_content] = ''.join(sections)

            # Otherwise...
            else:

                # ...format the type as a code literal:
                match = re.match(_LINE_REGEX, lines[index_return_type_content], flags=re.DOTALL)
                assert match, "'Return type' header must have some content below it."
                sections = list(match.groups())
                sections[1] = _bookend(sections[1], _CODE_LITERAL_CHARACTER)
                lines[index_return_type_content] = ''.join(sections)

                # ...delete the 'Return type' header and the extra lines that come before it:
                del lines[index_returns_header + 1 : index_return_type_header + 1]

        # Ensure all literal blocks get Python highlighting:
        in_literal_block = False
        _CODE_BLOCK_SYMBOL = '```'
        for index, line in enumerate(lines):
            if line.startswith(_CODE_BLOCK_SYMBOL):
                if not in_literal_block:
                    in_literal_block = True
                    lines[index] = _CODE_BLOCK_SYMBOL + 'python\n'
                else:
                    in_literal_block = False
        if in_literal_block:
            warnings.warn('Unclosed literal block in `%s`.'  % filename)
            continue
        # TODO: This temporary fix can be removed once the linked change appears in sphinx-markdown-builder's next release:
        # https://github.com/codejamninja/sphinx-markdown-builder/pull/43

        # Ensure that HTML output blocks get HTML highlighting:
        for index, line in enumerate(lines):
            if line.startswith('-> <html>') and index > 0 and lines[index - 1].startswith(_CODE_BLOCK_SYMBOL):
                lines[index - 1] = _CODE_BLOCK_SYMBOL + 'html\n'
        # TODO: This temporary fix can be removed once the linked change appears in sphinx-markdown-builder's next release:
        # https://github.com/codejamninja/sphinx-markdown-builder/pull/43

        # Ensure embedded images fit to the page:
        for index, line in enumerate(lines):
            match = re.match('!\[image]\((.*)\)', line, flags=re.DOTALL)
            if match:
                link = match.groups()[0]

                if link.startswith('\\') or link.startswith('./'): # (make the image path absolute if it's relative)
                    link = 'https://github.com/gmplot/gmplot/wiki/%s' % link[1:]

                lines[index] = '[[%s | width = 100000px]]\n' % link

        # Update the file:
        with open(directory + filename, mode='w', encoding='utf-8') as file:
            file.writelines(lines)
