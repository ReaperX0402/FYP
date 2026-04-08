from pathlib import Path
from src.ai_model.blur_detector import BlurDetector

# Folder containing your test images
IMAGE_FOLDER = Path("data/test_blur")

# Initialize detector (adjust threshold if needed)
detector = BlurDetector(threshold=70)

def main():
    if not IMAGE_FOLDER.exists():
        print(f"Folder not found: {IMAGE_FOLDER}")
        return

    print("=" * 60)
    print("Blur Detection Test")
    print("=" * 60)

    for img_path in sorted(IMAGE_FOLDER.iterdir()):
        if img_path.suffix.lower() not in [".jpg", ".jpeg", ".png"]:
            continue

        try:
            result = detector.detect(img_path)

            print(f"{img_path.name}")
            print(f"  Blur Score   : {result['blur_score']:.2f}")
            print(f"  Blur Warning : {'YES' if result['blur_warning'] else 'NO'}")
            print("-" * 60)

        except Exception as e:
            print(f"{img_path.name} -> ERROR: {e}")

if __name__ == "__main__":
    main()