"""Interactive SPARQL Query Browser widget for Jupyter notebooks."""

import re
import ipywidgets as widgets
from IPython.display import display, clear_output, HTML
from pathlib import Path
import pandas as pd

from .helper_functions import QueryEngine, load_query


def extract_local_name(uri):
    """Extract the local name from a URI by splitting on /, \\, or #."""
    if not isinstance(uri, str):
        return uri
    # Split by common URI delimiters and take the last part
    parts = re.split(r'[/\\#]', uri)
    return parts[-1] if parts else uri


def shorten_uris_to_local(df):
    """Replace all URIs in a DataFrame with just their local names."""
    result = df.copy()
    for col in result.columns:
        result[col] = result[col].apply(extract_local_name)
    return result


def parse_prefixes_from_query(query_text):
    """
    Parse PREFIX declarations from a SPARQL query.

    Args:
        query_text: SPARQL query string

    Returns:
        Dictionary mapping namespace URIs to prefixes (e.g., {'http://example.org/': 'ex:'})
    """
    # Match PREFIX declarations: PREFIX prefix: <uri>
    prefix_pattern = r'PREFIX\s+(\w+):\s*<([^>]+)>'
    matches = re.findall(prefix_pattern, query_text, re.IGNORECASE)

    # Build dict: namespace URI -> prefix:
    namespaces = {}
    for prefix, uri in matches:
        namespaces[uri] = f"{prefix}:"

    return namespaces


def replace_uris_with_prefixes(df, namespaces):
    """
    Replace URIs in a DataFrame with their prefixed versions.

    Args:
        df: pandas DataFrame with URI values
        namespaces: Dictionary mapping namespace URIs to prefixes

    Returns:
        DataFrame with URIs replaced by prefixed names
    """
    if not namespaces:
        return df

    result = df.copy()

    def replace_uri(value):
        if not isinstance(value, str):
            return value
        # Try each namespace, longest first to avoid partial matches
        for uri, prefix in sorted(namespaces.items(), key=lambda x: -len(x[0])):
            if value.startswith(uri):
                return value.replace(uri, prefix, 1)
        return value

    for col in result.columns:
        result[col] = result[col].apply(replace_uri)

    return result


# Default template for new queries
NEW_QUERY_TEMPLATE = '''PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX dici_onto: <https://digicities.info/ontology#>

SELECT *
WHERE {
    ?s ?p ?o .
}
LIMIT 100
'''


class QueryBrowser:
    """
    Interactive SPARQL query browser widget.

    Provides a UI for:
    - Browsing and selecting saved queries by category
    - Editing queries before execution
    - Running queries with/without inference
    - Creating and saving new queries
    - Saving modifications to existing queries
    """

    def __init__(self, client, queries_dir: Path):
        """
        Initialize the Query Browser.

        Args:
            client: GraphDBClient instance
            queries_dir: Path to the queries directory (e.g., data/03_queries)
        """
        self.client = client
        self.queries_dir = queries_dir
        self.engine = QueryEngine(client, queries_dir)

        # State
        self.current_queries = {}
        self.current_query_path = None
        self.original_query_text = ''
        self.is_new_query_mode = False

        # Build widgets
        self._create_widgets()
        self._connect_handlers()

    def _create_widgets(self):
        """Create all UI widgets."""

        # Get available categories
        categories = self.engine.categories()

        # Category selection
        self.category_dropdown = widgets.Dropdown(
            options=[('-- Select Category --', None)] + [(cat, cat) for cat in categories],
            value=None,
            description='Category:',
            style={'description_width': '80px'},
            layout=widgets.Layout(width='400px')
        )

        # Query selection
        self.query_dropdown = widgets.Dropdown(
            options=[('-- Select Query --', None)],
            value=None,
            description='Query:',
            style={'description_width': '80px'},
            layout=widgets.Layout(width='400px')
        )

        # New query button
        self.new_query_button = widgets.Button(
            description='New Query',
            button_style='success',
            icon='plus',
            layout=widgets.Layout(width='120px'),
            tooltip='Create a new query'
        )

        # Query editor
        self.query_editor = widgets.Textarea(
            value='',
            placeholder='Select a query or click "New Query" to start writing...',
            description='',
            layout=widgets.Layout(width='100%', height='250px'),
            style={'description_width': '0px'}
        )

        # New filename input (hidden by default)
        self.new_filename_input = widgets.Text(
            value='',
            placeholder='Enter query name (without .sparql)',
            description='Filename:',
            style={'description_width': '80px'},
            layout=widgets.Layout(width='400px', display='none')
        )

        # Inference checkbox
        self.infer_checkbox = widgets.Checkbox(
            value=True,
            description='Include Inferred (Reasoning)',
            indent=False,
            style={'description_width': 'initial'},
            layout=widgets.Layout(width='250px')
        )

        # Display options
        self.use_prefixes_checkbox = widgets.Checkbox(
            value=False,
            description='Use Namespace Prefixes',
            indent=False,
            style={'description_width': 'initial'},
            layout=widgets.Layout(width='200px'),
            tooltip='Replace full URIs with namespace prefixes (e.g., dici_onto:Component)'
        )

        self.local_names_checkbox = widgets.Checkbox(
            value=False,
            description='Local Names Only',
            indent=False,
            style={'description_width': 'initial'},
            layout=widgets.Layout(width='180px'),
            tooltip='Show only the local part of URIs (e.g., Component instead of full URI)'
        )

        # Status label for save feedback
        self.status_label = widgets.HTML(value='')

        # Mode indicator
        self.mode_label = widgets.HTML(value='')

        # Buttons
        self.run_button = widgets.Button(
            description='Run Query',
            button_style='primary',
            icon='play',
            layout=widgets.Layout(width='120px')
        )

        self.save_button = widgets.Button(
            description='Save',
            button_style='warning',
            icon='save',
            layout=widgets.Layout(width='100px'),
            tooltip='Save changes to existing file'
        )

        self.save_as_new_button = widgets.Button(
            description='Save As New',
            button_style='success',
            icon='file',
            layout=widgets.Layout(width='120px'),
            tooltip='Save as a new query file'
        )

        self.reset_button = widgets.Button(
            description='Reset',
            button_style='',
            icon='undo',
            layout=widgets.Layout(width='100px'),
            tooltip='Reset to original query'
        )

        # Output area for results
        self.output_area = widgets.Output()

    def _connect_handlers(self):
        """Connect event handlers to widgets."""
        self.category_dropdown.observe(self._on_category_change, names='value')
        self.query_dropdown.observe(self._on_query_change, names='value')
        self.query_editor.observe(self._on_editor_change, names='value')
        self.new_query_button.on_click(self._on_new_query_click)
        self.run_button.on_click(self._on_run_button_click)
        self.save_button.on_click(self._on_save_button_click)
        self.save_as_new_button.on_click(self._on_save_as_new_click)
        self.reset_button.on_click(self._on_reset_button_click)

    def _refresh_query_list(self):
        """Refresh the query dropdown with current queries."""
        if self.category_dropdown.value:
            self.current_queries = self.engine.select_category(self.category_dropdown.value)

            query_options = [('-- Select Query --', None)]
            for num, (name, path) in self.current_queries.items():
                query_options.append((f"[{num}] {name}", num))

            self.query_dropdown.options = query_options

    def _set_edit_mode(self):
        """Switch to edit existing query mode."""
        self.is_new_query_mode = False
        self.new_filename_input.layout.display = 'none'
        self.mode_label.value = ''
        self.save_button.layout.display = ''

    def _set_new_query_mode(self):
        """Switch to new query mode."""
        self.is_new_query_mode = True
        self.new_filename_input.layout.display = ''
        self.mode_label.value = '<span style="color: green; font-weight: bold;">NEW QUERY MODE</span>'
        self.save_button.layout.display = 'none'

    # === Event Handlers ===

    def _on_category_change(self, change):
        """Update query dropdown when category changes."""
        # Clear editor and status
        self.query_editor.value = ''
        self.status_label.value = ''
        self.current_query_path = None
        self.original_query_text = ''
        self.new_filename_input.value = ''
        self._set_edit_mode()

        if change['new'] is None:
            self.query_dropdown.options = [('-- Select Query --', None)]
            self.query_dropdown.value = None
            self.current_queries = {}
            return

        with self.output_area:
            clear_output()
            self.current_queries = self.engine.select_category(change['new'])

        # Update query dropdown
        query_options = [('-- Select Query --', None)]
        for num, (name, path) in self.current_queries.items():
            query_options.append((f"[{num}] {name}", num))

        self.query_dropdown.options = query_options
        self.query_dropdown.value = None

    def _on_query_change(self, change):
        """Load query text into editor when query is selected."""
        self.status_label.value = ''
        self._set_edit_mode()

        if change['new'] is None:
            self.query_editor.value = ''
            self.current_query_path = None
            self.original_query_text = ''
            return

        query_num = change['new']
        if query_num in self.current_queries:
            query_name, query_path = self.current_queries[query_num]
            self.current_query_path = query_path
            self.original_query_text = load_query(query_path)
            self.query_editor.value = self.original_query_text

            with self.output_area:
                clear_output()
                print(f"Loaded: {query_name}")
                print(f"File: {query_path.name}")

    def _on_new_query_click(self, b):
        """Start creating a new query."""
        if self.category_dropdown.value is None:
            self.status_label.value = '<span style="color: red;">Please select a category first.</span>'
            return

        # Clear selection and switch to new query mode
        self.query_dropdown.value = None
        self.current_query_path = None
        self.original_query_text = ''

        # Set up editor with template
        self.query_editor.value = NEW_QUERY_TEMPLATE
        self.new_filename_input.value = ''

        self._set_new_query_mode()
        self.status_label.value = '<span style="color: blue;">Enter a filename and write your query, then click "Save As New".</span>'

        with self.output_area:
            clear_output()
            print(f"Creating new query in category: {self.category_dropdown.value}")
            print("Enter a filename above and write your query.")

    def _on_run_button_click(self, b):
        """Run the query from the editor."""
        with self.output_area:
            clear_output()

            query_text = self.query_editor.value.strip()

            if not query_text:
                print("Please select or enter a query first.")
                return

            # Get query name for display
            if self.is_new_query_mode:
                query_name = self.new_filename_input.value or "New Query"
            elif self.query_dropdown.value and self.query_dropdown.value in self.current_queries:
                query_name = self.current_queries[self.query_dropdown.value][0]
            else:
                query_name = "Custom Query"

            # Get settings
            use_inference = self.infer_checkbox.value
            use_prefixes = self.use_prefixes_checkbox.value
            use_local_names = self.local_names_checkbox.value

            infer_status = "ON" if use_inference else "OFF"

            print(f"Running: {query_name}")
            print(f"Inference: {infer_status}")
            print("-" * 50)

            try:
                result = self.client.sparql_query(query_text, infer=use_inference)
                self.engine.last_result = result

                print(f"Results: {len(result)} rows")

                if not result.empty:
                    # Apply display transformations
                    display_result = result.copy()

                    if use_local_names:
                        # Local names only (takes precedence)
                        display_result = shorten_uris_to_local(display_result)
                    elif use_prefixes:
                        # Replace with namespace prefixes from the query
                        namespaces = parse_prefixes_from_query(query_text)
                        if namespaces:
                            display_result = replace_uris_with_prefixes(display_result, namespaces)
                        else:
                            print("(No PREFIX declarations found in query)")

                    print("")
                    # Display with full width and horizontal scrolling
                    self._display_dataframe(display_result)
                else:
                    print("\nQuery returned no results.")
                    if not use_inference:
                        print("TIP: Try enabling 'Include Inferred' checkbox for reasoning-based results.")

            except Exception as e:
                print(f"\nError running query: {e}")

    def _display_dataframe(self, df):
        """Display a DataFrame with full content and horizontal scrolling."""
        # Create HTML table with full content and scrollable container
        html_style = """
        <style>
            .scrollable-table {
                overflow-x: auto;
                max-width: 100%;
            }
            .scrollable-table table {
                border-collapse: collapse;
                font-size: 12px;
            }
            .scrollable-table th, .scrollable-table td {
                border: 1px solid #ddd;
                padding: 6px 10px;
                text-align: left;
                white-space: nowrap;
            }
            .scrollable-table th {
                background-color: #f5f5f5;
                font-weight: bold;
            }
            .scrollable-table tr:nth-child(even) {
                background-color: #fafafa;
            }
            .scrollable-table tr:hover {
                background-color: #f0f0f0;
            }
        </style>
        """
        html_table = df.to_html(index=True, escape=True, max_rows=None, max_cols=None)
        html_content = f'{html_style}<div class="scrollable-table">{html_table}</div>'
        display(HTML(html_content))

    def _on_save_button_click(self, b):
        """Save the edited query back to the existing file."""
        if self.current_query_path is None:
            self.status_label.value = '<span style="color: red;">No query file selected. Use "Save As New" to create a new file.</span>'
            return

        query_text = self.query_editor.value

        if query_text == self.original_query_text:
            self.status_label.value = '<span style="color: orange;">No changes to save.</span>'
            return

        try:
            with open(self.current_query_path, 'w', encoding='utf-8') as f:
                f.write(query_text)

            self.original_query_text = query_text
            self.status_label.value = f'<span style="color: green;">Saved to {self.current_query_path.name}</span>'

        except Exception as e:
            self.status_label.value = f'<span style="color: red;">Error saving: {e}</span>'

    def _on_save_as_new_click(self, b):
        """Save the query as a new file."""
        if self.category_dropdown.value is None:
            self.status_label.value = '<span style="color: red;">Please select a category first.</span>'
            return

        filename = self.new_filename_input.value.strip()

        if not filename:
            self.status_label.value = '<span style="color: red;">Please enter a filename.</span>'
            return

        # Ensure .sparql extension
        if not filename.endswith('.sparql'):
            filename = filename + '.sparql'

        # Build the full path
        category_path = self.queries_dir / self.category_dropdown.value
        new_file_path = category_path / filename

        # Check if file already exists
        if new_file_path.exists():
            self.status_label.value = f'<span style="color: red;">File "{filename}" already exists. Choose a different name or edit the existing query.</span>'
            return

        query_text = self.query_editor.value

        if not query_text.strip():
            self.status_label.value = '<span style="color: red;">Cannot save empty query.</span>'
            return

        try:
            # Ensure category directory exists
            category_path.mkdir(parents=True, exist_ok=True)

            with open(new_file_path, 'w', encoding='utf-8') as f:
                f.write(query_text)

            # Update state
            self.current_query_path = new_file_path
            self.original_query_text = query_text

            # Refresh query list
            with self.output_area:
                clear_output()
                self._refresh_query_list()

            # Switch back to edit mode
            self._set_edit_mode()
            self.new_filename_input.value = ''

            self.status_label.value = f'<span style="color: green;">Created new query: {filename}</span>'

            with self.output_area:
                print(f"Successfully created: {new_file_path.name}")
                print(f"Category: {self.category_dropdown.value}")
                print("\nThe query list has been refreshed.")

        except Exception as e:
            self.status_label.value = f'<span style="color: red;">Error creating file: {e}</span>'

    def _on_reset_button_click(self, b):
        """Reset the editor to the original query."""
        if self.is_new_query_mode:
            self.query_editor.value = NEW_QUERY_TEMPLATE
            self.status_label.value = '<span style="color: blue;">Reset to template.</span>'
        elif self.original_query_text:
            self.query_editor.value = self.original_query_text
            self.status_label.value = '<span style="color: blue;">Reset to original.</span>'
        else:
            self.status_label.value = '<span style="color: orange;">No original query to reset to.</span>'

    def _on_editor_change(self, change):
        """Update status when editor content changes."""
        if not self.is_new_query_mode and self.original_query_text and change['new'] != self.original_query_text:
            self.status_label.value = '<span style="color: orange;">Modified (unsaved)</span>'
        elif not self.is_new_query_mode and self.original_query_text:
            self.status_label.value = ''

    def display(self):
        """Display the query browser widget."""
        # Build layout
        selection_box = widgets.VBox([
            widgets.HTML('<h3>Query Selection</h3>'),
            self.category_dropdown,
            widgets.HBox([self.query_dropdown, self.new_query_button]),
        ])

        # Display options row
        display_options = widgets.HBox([
            widgets.HTML('<b>Display:</b>&nbsp;&nbsp;'),
            self.use_prefixes_checkbox,
            self.local_names_checkbox,
        ])

        editor_box = widgets.VBox([
            widgets.HBox([widgets.HTML('<h3>Query Editor</h3>'), self.mode_label]),
            self.new_filename_input,
            self.query_editor,
            widgets.HBox([self.run_button, self.infer_checkbox]),
            display_options,
            widgets.HBox([self.save_button, self.save_as_new_button, self.reset_button, self.status_label]),
        ])

        results_box = widgets.VBox([
            widgets.HTML('<h3>Results</h3>'),
            self.output_area,
        ])

        # Display everything
        display(selection_box)
        display(widgets.HTML('<hr>'))
        display(editor_box)
        display(widgets.HTML('<hr>'))
        display(results_box)
