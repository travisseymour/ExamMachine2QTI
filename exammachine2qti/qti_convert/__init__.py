from pathlib import Path
import tempfile
from zipfile import ZipFile
import os
from logzero import logger
from lxml import etree
from qti_convert import formats
from qti_convert.qti_parser import assessment_meta, item

"""
Traceback (most recent call last):
  File "/home/nogard/Dropbox/Documents/python_coding/exammachine2qti/exammachine2qti.py", line 242, in <module>
    qti_convert.qti2docx(zip_output_path, docx_output_path)
  File "/home/nogard/Dropbox/Documents/python_coding/exammachine2qti/qti_convert/__init__.py", line 40, in qti2docx
    formats.docx.write_file(qti_resource, output_file)
  File "/home/nogard/Dropbox/Documents/python_coding/exammachine2qti/qti_convert/formats/docx.py", line 22, in write_file
    html_parser.add_html_to_document(assessment['metadata']['description'], doc)
  File "/home/nogard/GLOBAL_VENVS/exammachine2qti/lib/python3.8/site-packages/htmldocx/h2d.py", line 458, in add_html_to_document
    raise ValueError('First argument needs to be a %s' % str)
ValueError: First argument needs to be a <class 'str'>

"""


def qti2docx(qti_zip_file_path: Path, output_file: Path):
    cwd = Path.cwd()
    try:
        with tempfile.TemporaryDirectory() as tmp_folder_name:
            tmp_folder = Path(tmp_folder_name)
            with ZipFile(qti_zip_file_path, "r") as zipObj:
                zipObj.extractall(tmp_folder)

            imsmnifest = Path(tmp_folder, "imsmanifest.xml").resolve()
            os.chdir(imsmnifest.parent)
            xml_doc = etree.parse(str(imsmnifest))

            qti_resource = {"assessment": []}

            for xml_resource in xml_doc.getroot().findall(
                ".//{http://www.imsglobal.org/xsd/imsccv1p1/imscp_v1p1}resource[@type='imsqti_xmlv1p2']"
            ):
                this_assessment = {
                    "id": xml_resource.get("identifier"),
                    "metadata": assessment_meta.get_metadata(
                        xml_resource.get("identifier") + "/" + "assessment_meta.xml"
                    ),
                    "question": [],
                }

                this_assessment_xml = this_assessment["id"] + "/" + this_assessment["id"] + ".xml"

                for xml_item in (
                    etree.parse(this_assessment_xml)
                    .getroot()
                    .findall(".//{http://www.imsglobal.org/xsd/ims_qtiasiv1p2}item")
                ):
                    this_assessment["question"].append(item.get_question(xml_item))

                qti_resource["assessment"].append(this_assessment)

            formats.docx.write_file(qti_resource, output_file)

    except OSError as e:
        logger.error("%s", e)

    except etree.ParseError as e:
        logger.error("XML parser error: %s", e)

    finally:
        os.chdir(cwd)
