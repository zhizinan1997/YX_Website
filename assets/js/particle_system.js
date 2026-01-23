
class NeuralParticleSystem {
    constructor(containerId, config = {}) {
        this.container = document.getElementById(containerId);
        this.config = Object.assign({
            effect: "default",
            effectMode: 0,
            particleSize: 200,
            uploadedImage: null
        }, config);

        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.particles = null;
        this.rafId = null;
        this.mouse = new THREE.Vector2();
        this.targetMouse = new THREE.Vector2();

        // Internal state
        this.particleTexture = null;

        this.init();
        this.addEventListeners();
    }

    init() {
        // Scene setup
        this.scene = new THREE.Scene();

        // Camera setup
        this.camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
        this.camera.position.z = 300;

        // Renderer setup
        this.renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
        this.renderer.setSize(window.innerWidth, window.innerHeight);
        this.renderer.setPixelRatio(window.devicePixelRatio);
        this.container.appendChild(this.renderer.domElement);

        // Load default texture if image provided
        if (this.config.uploadedImage) {
            this.updateImage(this.config.uploadedImage);
        }

        this.animate();
    }

    createParticles(imageData) {
        if (this.particles) {
            this.scene.remove(this.particles);
            this.particles.geometry.dispose();
            this.particles.material.dispose();
        }

        const geometry = new THREE.BufferGeometry();
        const positions = [];
        const colors = [];
        const sizes = []; // Use sizes for additional effect variation if needed

        const width = imageData.width;
        const height = imageData.height;
        const data = imageData.data;

        // Create particles based on bright pixels
        const threshold = 30; // Brightness threshold
        const gap = 3; // Pixel skipping for performance/aesthetics (Reduced from 4 to 3 for higher density)

        for (let y = 0; y < height; y += gap) {
            for (let x = 0; x < width; x += gap) {
                const index = (y * width + x) * 4;
                const r = data[index];
                const g = data[index + 1];
                const b = data[index + 2];
                const brightness = (r + g + b) / 3;

                if (brightness > threshold) {
                    // Center the image
                    const posX = x - width / 2;
                    const posY = -(y - height / 2); // Invert Y
                    const posZ = (Math.random() - 0.5) * 50; // Slight depth variation

                    positions.push(posX, posY, posZ);

                    // Normalize color
                    colors.push(r / 255, g / 255, b / 255);

                    sizes.push(1.0);
                }
            }
        }

        geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
        geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));

        // Save original positions for animation effects
        geometry.setAttribute('initialPosition', new THREE.Float32BufferAttribute(positions, 3));

        // Shader Material for advanced particle behavior
        const material = new THREE.PointsMaterial({
            size: 2, // Base size
            vertexColors: true,
            blending: THREE.AdditiveBlending,
            depthTest: false,
            transparent: true,
            opacity: 0.8
        });

        this.particles = new THREE.Points(geometry, material);
        this.scene.add(this.particles);
    }

    updateImage(imageSource) {
        const loader = new THREE.TextureLoader();

        // Handle both URL and Base64
        loader.load(imageSource, (texture) => {
            // Get image data
            const img = texture.image;
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');

            // Limit size for performance
            const maxSize = 400; // Adjust quality vs performance
            let w = img.width;
            let h = img.height;

            if (w > h) {
                if (w > maxSize) {
                    h = Math.round(h * (maxSize / w));
                    w = maxSize;
                }
            } else {
                if (h > maxSize) {
                    w = Math.round(w * (maxSize / h));
                    h = maxSize;
                }
            }

            canvas.width = w;
            canvas.height = h;
            ctx.drawImage(img, 0, 0, w, h);

            const imageData = ctx.getImageData(0, 0, w, h);
            this.createParticles(imageData);
        });
    }

    addEventListeners() {
        window.addEventListener('resize', this.onWindowResize.bind(this));
        // Mouse interaction removed as per user request
    }

    onWindowResize() {
        this.camera.aspect = window.innerWidth / window.innerHeight;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(window.innerWidth, window.innerHeight);
    }

    onMouseMove(event) {
        // Disabled
    }

    animate() {
        this.rafId = requestAnimationFrame(this.animate.bind(this));

        // Smooth mouse movement - Disabled
        // this.mouse.x += (this.targetMouse.x - this.mouse.x) * 0.05;
        // this.mouse.y += (this.targetMouse.y - this.mouse.y) * 0.05;

        // Rotate scene slightly based on mouse
        if (this.particles) {
            this.particles.rotation.x += 0.001;
            this.particles.rotation.y += 0.002;

            // Interactive movement - Disabled
            // this.particles.rotation.x += this.mouse.y * 0.05;
            // this.particles.rotation.y += this.mouse.x * 0.05;

            // Basic "breathing" or noise effect on positions
            const positions = this.particles.geometry.attributes.position.array;
            const initialPositions = this.particles.geometry.attributes.initialPosition.array;
            const time = Date.now() * 0.001;

            for (let i = 0; i < positions.length; i += 3) {
                // Return to original position with some noise
                positions[i] = initialPositions[i] + Math.sin(time + initialPositions[i] * 0.5) * 2;
                positions[i + 1] = initialPositions[i + 1] + Math.cos(time + initialPositions[i + 1] * 0.5) * 2;
                positions[i + 2] = initialPositions[i + 2] + Math.sin(time + initialPositions[i + 2] * 0.5) * 2;
            }
            this.particles.geometry.attributes.position.needsUpdate = true;
        }

        this.renderer.render(this.scene, this.camera);
    }
}
