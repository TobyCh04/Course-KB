"""
Cornell KB — Diagram Extraction Script

Extracts images/diagrams from PDFs and generates structured descriptions
using Qwen3-VL via Ollama. Descriptions are stored as searchable facts.

Usage:
    python diagrams.py lecture_slides.pdf --course "SYSEN 5100" --lecture 1
    python diagrams.py lecture_slides.pdf --output diagram_facts.json
"""

import argparse
import base64
import json
import os
import sys
import tempfile
import urllib.request

OLLAMA_URL = "http://100.104.205.105:11434/api/generate"
VISION_MODEL = "qwen3-vl:8b"

DIAGRAM_PROMPTS = {
    "block_diagram": "Describe this block diagram in detail: identify all blocks/components with their labels, all connections and arrows showing signal flow, any equations or transfer functions shown, and the overall system being represented.",
    "flowchart": "Describe this flowchart: identify each step, decision point, arrows showing flow direction, start/end points, and any annotations or labels.",
    "circuit": "Describe this circuit diagram: identify all components (resistors, capacitors, op-amps, etc.), their values, connections between them, and the overall circuit function.",
    "graph": "Describe this graph/plot: identify the axes labels and units, all data series with their labels, trends observed, key data points, and any equations or annotations.",
    "equation": "Read all equations and formulas shown in this image. Output them in standard mathematical notation.",
    "matlab": "Describe this MATLAB/Simulink output: identify the system being simulated, parameters shown, key observations from the plots.",
    "general": "Describe this technical diagram in detail: what type of diagram is it, what are the main components, what relationships are shown, what labels/values/equations appear? Include all text visible in the image.",
}


def detect_diagram_type(image_path, ollama_url=OLLAMA_URL, model=VISION_MODEL):
    """Use vision model to classify the diagram type."""
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    prompt = "Classify this image into ONE of these categories: block_diagram, flowchart, circuit, graph, equation, matlab, general. Reply with ONLY the category name."

    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "images": [img_b64],
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 20}
    }).encode()

    req = urllib.request.Request(ollama_url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read())

    response = result.get("response", "").strip().lower()
    # Extract just the category
    for category in DIAGRAM_PROMPTS:
        if category in response:
            return category
    return "general"


def describe_diagram(image_path, diagram_type=None, ollama_url=OLLAMA_URL, model=VISION_MODEL):
    """Generate a structured description of a diagram using vision model."""
    # Resize if too large (Ollama has ~20MB image limit)
    from PIL import Image
    img = Image.open(image_path)
    max_dim = 2048
    if img.width > max_dim or img.height > max_dim:
        ratio = min(max_dim / img.width, max_dim / img.height)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)
        resized_path = image_path.replace(".png", "_resized.png")
        img.save(resized_path, "PNG")
        image_path = resized_path

    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    if diagram_type is None:
        diagram_type = detect_diagram_type(image_path, ollama_url, model)

    prompt = DIAGRAM_PROMPTS.get(diagram_type, DIAGRAM_PROMPTS["general"])

    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "images": [img_b64],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 1024}
    }).encode()

    req = urllib.request.Request(ollama_url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        result = json.loads(resp.read())

    return result.get("response", ""), diagram_type


def extract_images_from_pdf(pdf_path, output_dir=None):
    """Extract all images from a PDF. Returns list of (page_num, img_index, img_path)."""
    import pymupdf

    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="cornell_kb_diagrams_")

    doc = pymupdf.open(pdf_path)
    images = []

    for page_num in range(len(doc)):
        page = doc[page_num]

        # Check if page has text blocks (digital text)
        text_dict = page.get_text("dict")
        text_blocks = [b for b in text_dict["blocks"] if b.get("type") == 0 and b.get("text", "").strip()]
        image_blocks = [b for b in text_dict["blocks"] if b.get("type") == 1]

        # Extract embedded images
        page_images = page.get_images(full=True)
        for img_index, img in enumerate(page_images):
            xref = img[0]
            try:
                pix = pymupdf.Pixmap(doc, xref)
                # Skip tiny images (icons, decorations)
                if pix.width < 100 or pix.height < 100:
                    continue
                img_path = os.path.join(output_dir, f"page{page_num+1}_img{img_index+1}.png")
                pix.save(img_path)
                images.append((page_num + 1, img_index + 1, img_path))
            except Exception as e:
                print(f"  Warning: couldn't extract image {img_index+1} from page {page_num+1}: {e}")

        # If page has no text and is likely a scanned diagram, render entire page
        if not text_blocks and (page_images or image_blocks):
            pix = page.get_pixmap(dpi=150)
            img_path = os.path.join(output_dir, f"page{page_num+1}_full.png")
            pix.save(img_path)
            images.append((page_num + 1, 0, img_path))  # 0 = full page

    doc.close()
    return images


def process_pdf_diagrams(pdf_path, course_code, lecture, ollama_url=OLLAMA_URL, model=VISION_MODEL):
    """Extract and describe all diagrams from a PDF. Returns list of facts."""
    print(f"Extracting images from {pdf_path}...")
    images = extract_images_from_pdf(pdf_path)
    print(f"Found {len(images)} images")

    facts = []
    for page_num, img_index, img_path in images:
        label = f"page {page_num}" + (f", image {img_index}" if img_index > 0 else " (full page)")
        print(f"\nProcessing {label}...")

        try:
            description, diagram_type = describe_diagram(img_path, ollama_url=ollama_url, model=model)
            print(f"  Type: {diagram_type}")
            print(f"  Description: {description[:150]}...")

            facts.append({
                "content": description,
                "topic": f"diagram: {diagram_type}",
                "type": "diagram",
                "course": course_code,
                "lecture": lecture,
                "source_type": "diagram",
                "diagram_type": diagram_type,
                "page": page_num,
                "source_file": os.path.basename(pdf_path),
                "engine": model,
            })
        except Exception as e:
            print(f"  Error: {e}")

        # Cleanup temp image
        try:
            os.remove(img_path)
        except:
            pass

    return facts


def main():
    parser = argparse.ArgumentParser(description="Extract and describe diagrams from PDFs")
    parser.add_argument("pdf", help="Path to PDF file")
    parser.add_argument("--course", required=True, help="Course code")
    parser.add_argument("--lecture", type=int, required=True, help="Lecture number")
    parser.add_argument("--output", default=None, help="Output JSON file path")
    parser.add_argument("--ollama-url", default=OLLAMA_URL, help="Ollama API URL")
    parser.add_argument("--model", default=VISION_MODEL, help="Vision model")

    args = parser.parse_args()

    facts = process_pdf_diagrams(
        args.pdf,
        args.course,
        args.lecture,
        ollama_url=args.ollama_url,
        model=args.model,
    )

    print(f"\nTotal diagram facts: {len(facts)}")

    # Save
    if args.output:
        output_path = args.output
    else:
        base = os.path.splitext(os.path.basename(args.pdf))[0]
        output_path = os.path.join(os.path.dirname(args.pdf), f"{base}_diagrams.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(facts, f, indent=2, ensure_ascii=False)

    print(f"Saved to {output_path}")


if __name__ == "__main__":
    main()
