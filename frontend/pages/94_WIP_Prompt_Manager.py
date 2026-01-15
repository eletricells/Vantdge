"""
Prompt Manager - View and edit AI prompt templates
"""
import streamlit as st
import sys
from pathlib import Path

# Add paths
frontend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(frontend_dir))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from auth import check_password, check_page_access, show_access_denied
from src.prompts import get_prompt_manager, PromptManager
from datetime import datetime
import shutil

st.set_page_config(
    page_title="Prompt Manager",
    page_icon="📝",
    layout="wide"
)

# Password protection
if not check_password():
    st.stop()

# Page access check
if not check_page_access("WIP_Prompt_Manager"):
    show_access_denied()

st.title("📝 Prompt Manager")
st.markdown("View and edit AI prompt templates used by agents")
st.markdown("---")

# Initialize prompt manager
try:
    pm = get_prompt_manager()
    templates_dir = Path(pm.templates_dir)
except Exception as e:
    st.error(f"Failed to initialize PromptManager: {e}")
    st.stop()

# Get all categories
categories = []
for item in templates_dir.iterdir():
    if item.is_dir() and not item.name.startswith('_'):
        template_count = len(list(item.rglob("*.j2")))
        if template_count > 0:
            categories.append({
                "name": item.name,
                "count": template_count
            })

categories = sorted(categories, key=lambda x: x["name"])

# Sidebar - Category selection
with st.sidebar:
    st.markdown("## 📁 Categories")
    
    # Show category stats
    total_templates = sum(c["count"] for c in categories)
    st.metric("Total Templates", total_templates)
    st.metric("Categories", len(categories))
    
    st.markdown("---")
    
    # Category selector
    category_options = ["All Categories"] + [f"{c['name']} ({c['count']})" for c in categories]
    selected_category_display = st.selectbox("Select Category", category_options)
    
    if selected_category_display == "All Categories":
        selected_category = None
    else:
        selected_category = selected_category_display.split(" (")[0]
    
    st.markdown("---")
    
    # Search
    search_query = st.text_input("🔍 Search templates", "")
    
    st.markdown("---")
    st.markdown("""
    ### 💡 Tips
    - Templates use **Jinja2** syntax
    - Variables: `{{ variable }}`
    - Includes: `{% include '...' %}`
    - Filters: `{{ var | to_json }}`
    """)

# Main content - Template list and editor
col_list, col_editor = st.columns([1, 2])

# Get templates
templates = []
if selected_category:
    search_dir = templates_dir / selected_category
    if search_dir.exists():
        template_files = list(search_dir.rglob("*.j2"))
else:
    template_files = list(templates_dir.rglob("*.j2"))

for template_path in template_files:
    rel_path = template_path.relative_to(templates_dir)
    # Skip partials in the main list
    if '_partials' in str(rel_path) or '_backups' in str(rel_path):
        continue
    
    parts = rel_path.parts
    cat = parts[0] if len(parts) > 1 else "root"
    name = template_path.stem
    
    # Apply search filter
    if search_query and search_query.lower() not in name.lower() and search_query.lower() not in cat.lower():
        continue
    
    templates.append({
        "name": name,
        "category": cat,
        "path": str(rel_path).replace('\\', '/'),
        "full_path": str(template_path)
    })

templates = sorted(templates, key=lambda x: (x["category"], x["name"]))

# Template selection
with col_list:
    st.markdown("### 📄 Templates")
    
    if not templates:
        st.info("No templates found. Try adjusting your filters.")
    else:
        st.caption(f"Found {len(templates)} templates")
        
        # Group by category for display
        current_cat = None
        for tmpl in templates:
            if tmpl["category"] != current_cat:
                current_cat = tmpl["category"]
                st.markdown(f"**{current_cat}/**")
            
            # Use button for selection
            btn_key = f"select_{tmpl['path']}"
            if st.button(f"  📄 {tmpl['name']}", key=btn_key, width='stretch'):
                st.session_state['selected_template'] = tmpl

# Template editor
with col_editor:
    st.markdown("### ✏️ Editor")
    
    if 'selected_template' not in st.session_state:
        st.info("👈 Select a template from the list to view and edit")
    else:
        tmpl = st.session_state['selected_template']
        template_path = Path(tmpl['full_path'])
        
        st.markdown(f"**{tmpl['category']}/{tmpl['name']}.j2**")
        
        # Load content
        try:
            content = template_path.read_text(encoding='utf-8')
        except Exception as e:
            st.error(f"Failed to read template: {e}")
            content = ""
        
        # Editor
        edited_content = st.text_area(
            "Template Content",
            value=content,
            height=500,
            key=f"editor_{tmpl['path']}"
        )
        
        # Action buttons
        col_save, col_reset, col_preview = st.columns(3)

        with col_save:
            if st.button("💾 Save Changes", type="primary", width='stretch'):
                if edited_content != content:
                    try:
                        # Create backup
                        backup_dir = templates_dir / "_backups" / tmpl['category']
                        backup_dir.mkdir(parents=True, exist_ok=True)
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        backup_path = backup_dir / f"{tmpl['name']}_{timestamp}.j2.bak"
                        shutil.copy2(template_path, backup_path)

                        # Save new content
                        template_path.write_text(edited_content, encoding='utf-8')

                        # Clear PromptManager cache
                        if pm._cache is not None:
                            pm._cache.clear()

                        st.success(f"✅ Saved! Backup created at: {backup_path.name}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to save: {e}")
                else:
                    st.info("No changes to save")

        with col_reset:
            if st.button("🔄 Reset", width='stretch'):
                st.rerun()

        with col_preview:
            show_preview = st.button("👁️ Preview", width='stretch')

        # Preview section
        if show_preview:
            st.markdown("---")
            st.markdown("### 🔍 Preview (with sample variables)")

            # Try to render with empty/sample variables
            try:
                # Find variables in template
                import re
                var_pattern = r'\{\{\s*(\w+)'
                vars_found = set(re.findall(var_pattern, edited_content))

                # Create sample data for common variables
                sample_vars = {}
                for var in vars_found:
                    if 'name' in var.lower():
                        sample_vars[var] = "Sample Name"
                    elif 'disease' in var.lower():
                        sample_vars[var] = "Sample Disease"
                    elif 'drug' in var.lower():
                        sample_vars[var] = "Sample Drug"
                    elif 'result' in var.lower() or 'search' in var.lower():
                        sample_vars[var] = [{"title": "Sample result", "content": "Sample content"}]
                    elif 'paper' in var.lower():
                        sample_vars[var] = [{"num": 1, "title": "Sample paper", "abstract": "Sample abstract"}]
                    elif 'context' in var.lower():
                        sample_vars[var] = {"key": "value"}
                    else:
                        sample_vars[var] = f"[{var}]"

                st.caption(f"Variables found: {', '.join(vars_found) if vars_found else 'None'}")

                rendered = pm.render(tmpl['path'].replace('.j2', ''), **sample_vars)
                st.code(rendered, language="markdown")
            except Exception as e:
                st.error(f"Preview error: {e}")
                st.code(edited_content, language="jinja2")

        # Show partials if available
        partials_dir = templates_dir / tmpl['category'] / "_partials"
        if partials_dir.exists():
            with st.expander("📎 Available Partials"):
                for partial_path in partials_dir.glob("*.j2"):
                    st.markdown(f"**{partial_path.name}**")
                    st.code(partial_path.read_text(encoding='utf-8'), language="jinja2")

# Footer
st.markdown("---")
st.markdown("""
**Template Syntax Reference:**
- `{{ variable }}` - Insert variable value
- `{{ variable | to_json }}` - Format as JSON
- `{{ variable | join_list }}` - Join list with commas
- `{% include 'category/_partials/name.j2' %}` - Include partial template
- `{% if condition %}...{% endif %}` - Conditional blocks
- `{% for item in list %}...{% endfor %}` - Loops
""")

