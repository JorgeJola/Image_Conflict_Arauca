from flask import Blueprint, Flask, render_template, request, redirect, url_for, send_file
import tempfile
import os
import zipfile
import geopandas as gpd

main = Blueprint('main', __name__)

UPLOAD_FOLDER = tempfile.mkdtemp()
RESULT_FOLDER = tempfile.mkdtemp()
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULT_FOLDER, exist_ok=True)


def extract_shapefile(zip_path, extract_folder):
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_folder)
        shapefiles = [
            os.path.join(root, file)
            for root, _, files in os.walk(extract_folder)
            for file in files if file.endswith('.shp') and not file.startswith('._')
        ]
        return shapefiles[0] if shapefiles else None
    except Exception as e:
        print(f"Error extracting shapefile: {e}")
        return None


@main.route('/', methods=['GET', 'POST'])
def conflict():
    if request.method == 'POST':
        file1 = request.files.get('file1')
        if not file1:
            return "Error: No file uploaded", 400

        file1_path = os.path.join(UPLOAD_FOLDER, file1.filename)
        file1.save(file1_path)

        extract_folder = os.path.join(UPLOAD_FOLDER, 'file1')
        os.makedirs(extract_folder, exist_ok=True)
        shapefile1 = extract_shapefile(file1_path, extract_folder)

        if not shapefile1:
            return "Error: No valid shapefile found in the uploaded file", 400

        try:
            gdf1 = gpd.read_file(shapefile1)
            gdf2 = gpd.read_file(
                os.path.join('Image_Conflict_Arauca', 'static', 'vocation', 'vocation_Arauca.shp')
            )

            if gdf1.crs != gdf2.crs:
                gdf1 = gdf1.to_crs(gdf2.crs)

            result = gpd.sjoin(
                gdf1, gdf2[['geometry', 'Vocacion']], how='left', predicate='intersects'
            )

            labels_dict = {
                'Agricultural Areas': '24', 'Continental Waters': '51',
                'Continental Wetlands': '41', 'Forest': '31',
                'Industry and Commercial': '12', 'Little vegetation areas': '33',
                'Mining': '13', 'Pastures': '23', 'Shrublands and Grassland': '32',
                'Urban Zones': '11',
            }
            result['Level 2'] = result['class'].replace(labels_dict)

            def assign_conflict(row):
                conflict_mapping = {
                    "Agrícola": {"High": ["11", "12", "13", "31", "33", "41", "51"],
                                 "Moderate": ["32", "22"],
                                 "No Conflict": ["21", "23", "24"]},
                    "Ganadera": {"High": ["11", "12", "13", "31", "41", "51"],
                                 "Moderate": ["21", "23", "24", "32", "33"],
                                 "No Conflict": ["22"]},
                    "Agroforestal": {"High": ["11", "12", "13", "41", "51"],
                                     "Moderate": ["21", "22", "33"],
                                     "No Conflict": ["23", "24", "31", "32"]},
                    "Forestal": {"High": ["11", "12", "13", "21", "22", "23", "24"],
                                 "Moderate": ["33"],
                                 "No Conflict": ["31", "32", "41", "51"]},
                    "Conservación de Suelos": {"High": ["11", "12", "13", "41", "51"],
                                               "Moderate": ["21", "22", "33"],
                                               "No Conflict": ["23", "24", "31", "32"]},
                    "Cuerpo de agua": {"High": ["11", "12", "13", "21", "22", "23", "24", "31", "32", "33"],
                                       "No Conflict": ["41", "51"]},
                    "Zonas urbanas": {"High": ["11", "12", "13", "21", "22", "23", "24", "31", "32", "33", "41", "51"]},
                }
                for level, values in conflict_mapping.get(row["Vocacion"], {}).items():
                    if row["Level 2"] in values:
                        return level
                return "Unknown"

            result["Conflict_Level"] = result.apply(assign_conflict, axis=1)

            output_path = os.path.join(RESULT_FOLDER, 'conflict')
            result.to_file(f"{output_path}.shp")
            zip_filename = f"{output_path}.zip"
            with zipfile.ZipFile(zip_filename, 'w') as zipf:
                for ext in ['.shp', '.shx', '.dbf', '.prj']:
                    file_path = f"{output_path}{ext}"
                    if os.path.exists(file_path):
                        zipf.write(file_path, os.path.basename(file_path))

            return redirect(url_for('main.download_file', filename=os.path.basename(zip_filename)))

        except Exception as e:
            print(f"Error processing shapefiles: {e}")
            return "Error processing the shapefiles", 500

    return render_template('change.html')


@main.route('/download/<filename>')
def download_file(filename):
    file_path = os.path.join(RESULT_FOLDER, filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return "Error: File not found", 404
