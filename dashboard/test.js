// ============================================================================
// Three.js 3D HUD 씬 설정 및 상호작용
// ============================================================================

// ============================================================================
// 설정 중앙화
// ============================================================================
const CONFIG = {
    scene: {
        fov: 65,
        fogDensity: 0,
        bgColor: "개인별bg",
        fogColor: "fog"
    },
    camera: {
        initialPos: {x: 10, y: -8, z: 60},
        target: { x: 0, y: 0, z: 5 },
        zoomDist: 20
    },
    pentagon: {
        radius: 18,
        thickness: 0.5,
        center: { x: 0, y: 0, z: 5 }
    },
    pentagon_fill: {
        opacity: 0.75,
        emissiveIntensity: 0.8,
        bevelEnabled: true,
        thickness: 0.5,
        color : "5각형3dmesh"
    },
    stars: {
        size: 0.8,
        roughness: 0.3,
        metalness: 0.6
    },
    circle: {
        big: 25,
        mid: 20,
        small: 15,
        thickness: 0.5,
        colorName: "원"
    },
    light: {
        ambientIntensity: 0.9,
        pointIntensity: 1.5,
        pointPos: { x: 20, y: 20, z: 20 }
    }
};

// ============================================================================
// 유틸리티 함수
// ============================================================================
function getCSSColorAsHex(colorName) {
    const cssVarName = `--color-${colorName}`;
    const cssValue = getComputedStyle(document.documentElement).getPropertyValue(cssVarName).trim();

    if (!cssValue) return 0xffffff;

    // 1. HEX (#ffffff, #fff)
    if (cssValue.startsWith('#')) {
        const hex = cssValue.substring(1);
        if (hex.length === 3) {
            const r = parseInt(hex[0] + hex[0], 16);
            const g = parseInt(hex[1] + hex[1], 16);
            const b = parseInt(hex[2] + hex[2], 16);
            return (r << 16) | (g << 8) | b;
        }
        return parseInt(hex, 16);
    }

    // 2. RGB / RGBA (rgba(r, g, b, a) 또는 rgb(r, g, b))
    const rgbaMatch = cssValue.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*(\d*\.?\d+))?\s*\)/i);
    if (rgbaMatch) {
        const r = parseInt(rgbaMatch[1], 10);
        const g = parseInt(rgbaMatch[2], 10);
        const b = parseInt(rgbaMatch[3], 10);
        return (r << 16) | (g << 8) | b;
    }

    // 3. Three.js 내장 파서를 활용한 예외 처리 (CSS 표준 색상명 등 대응)
    try {
        return new THREE.Color(cssValue).getHex();
    } catch {
        return 0xffffff;
    }
}

function getCSSColorWithOpacity(colorName) {
    const cssVarName = `--color-${colorName}`;
    const cssValue = getComputedStyle(document.documentElement).getPropertyValue(cssVarName).trim();

    if (!cssValue) {
        return { color: 0xffffff, opacity: 1 };
    }

    if (cssValue.startsWith('#')) {
        const hex = cssValue.substring(1);
        const normalized = hex.length === 3
            ? hex.split('').map(ch => ch + ch).join('')
            : hex;

        const r = parseInt(normalized.substring(0, 2), 16);
        const g = parseInt(normalized.substring(2, 4), 16);
        const b = parseInt(normalized.substring(4, 6), 16);

        return { color: (r << 16) | (g << 8) | b, opacity: 1 };
    }

    const rgbaMatch = cssValue.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*(\d*\.?\d+))?\s*\)/i);
    if (rgbaMatch) {
        const r = parseInt(rgbaMatch[1], 10);
        const g = parseInt(rgbaMatch[2], 10);
        const b = parseInt(rgbaMatch[3], 10);
        const a = rgbaMatch[4] !== undefined ? Number(rgbaMatch[4]) : 1;
        return { color: (r << 16) | (g << 8) | b, opacity: a };
    }

    try {
        const parsed = new THREE.Color(cssValue);
        return { color: parsed.getHex(), opacity: 1 };
    } catch {
        return { color: 0xffffff, opacity: 1 };
    }
}
// 1. 사용할 점들을 반환하는 함수( 오각형)
function createPentagonStarData(options = {}) {
    const radius = options.radius ?? CONFIG.pentagon.radius;
    const center = options.center ?? CONFIG.pentagon.center;

    // exType으로 전달받거나 기본값 사용 (indiv: 개인 측정치, M_base: 기준/평균 수치)
    const rawItems = options.exType ?? [
        { name: "BMI", nameEn: "bmi", indiv: 88, M_base: 100 },
        { name: "유연성", nameEn: "유연성", indiv: 99, M_base: 100 },
        { name: "심폐지구력", nameEn: "심폐지구력", indiv: 94, M_base: 100 },
        { name: "근력", nameEn: "근력", indiv: 76, M_base: 100 },
        { name: "근지구력", nameEn: "근지구력", indiv: 88, M_base: 100 }
    ];

    const startAngleDeg = 90;
    const stepDeg = 72;

    const indivPoints = [];
    const basePoints = [];

    rawItems.forEach((item, index) => {
        const angleDeg = startAngleDeg - (index * stepDeg);
        const angleRad = (angleDeg * Math.PI) / 180;

        // 평면 오각형으로 만들기 위해 z 값을 모두 동일하게 유지
        const flatZ = center.z;

        // 1. 개인 측정치(indiv)에 해당하는 3D 좌표 계산
        const indivRadius = radius * (item.indiv / 100);
        indivPoints.push({
            ...item,
            x: Number((center.x + indivRadius * Math.cos(angleRad)).toFixed(2)),
            y: Number((center.y + indivRadius * Math.sin(angleRad)).toFixed(2)),
            z: flatZ
        });

        // 2. 기준 수치(M_base)에 해당하는 3D 좌표 계산
        const baseRadius = radius * (item.M_base / 100);
        basePoints.push({
            ...item,
            x: Number((center.x + baseRadius * Math.cos(angleRad)).toFixed(2)),
            y: Number((center.y + baseRadius * Math.sin(angleRad)).toFixed(2)),
            z: flatZ
        });
    });

    return {
        indivPoints, // 개인 수치 기반 5개 좌표 배열
        basePoints   // M_base 수치 기반 5개 좌표 배열
    };
}
// 2. 방사형 오각형 채우기 3dMesh 생성 함수 (평면 오각형을 기준으로 3D Mesh 생성)
function createPentagonFillMesh(indivPoints, options = {}) {
    const config = { ...CONFIG.pentagon_fill, ...options };

    if (!indivPoints || indivPoints.length < 5) {
        console.error("createPentagonFillMesh: 5개의 점 좌표가 필요합니다.");
        return null;
    }

    // 평면 오각형을 우선 생성하고, 이를 3D mesh로 변환한다.
    const shape = new THREE.Shape();
    shape.moveTo(indivPoints[0].x, indivPoints[0].y);

    for (let i = 1; i < indivPoints.length; i++) {
        shape.lineTo(indivPoints[i].x, indivPoints[i].y);
    }
    shape.closePath();

    const extrudeSettings = {
        depth: config.thickness ?? 0.2,
        bevelEnabled: config.bevelEnabled ?? true,
        bevelThickness: 0.05,
        bevelSize: 0.05,
        bevelSegments: 3
    };

    const geometry = new THREE.ExtrudeGeometry(shape, extrudeSettings);
    const { color: baseColor, opacity } = getCSSColorWithOpacity(config.color ?? "cyan");
    const material = new THREE.MeshStandardMaterial({
        color: baseColor,
        emissive: baseColor,
        emissiveIntensity: config.emissiveIntensity ?? 0.6,
        roughness: 0.3,
        metalness: 0.2,
        transparent: opacity < 1,
        opacity,
        side: THREE.DoubleSide
    });

    const mesh = new THREE.Mesh(geometry, material);

    // 점들의 z 값이 모두 같아졌으므로, mesh도 같은 평면에서 만들면 안정적임
    const avgZ = indivPoints.reduce((acc, p) => acc + (p.z || 0), 0) / indivPoints.length;
    const zOffset = options.zOffset ?? 0;
    mesh.position.z = avgZ + zOffset;

    return mesh;
}
// 4. 원형 Ring Mesh 생성 함수
function createCircle(radius, thickness, colorName) {
    // 안쪽 반지름과 바깥쪽 반지름으로 중심 반지름(radius)과 튜브 두께(tubeRadius) 계산
    // TorusGeometry(중심반지름, 관두께, 원통단면세그먼트, 원둘레세그먼트)
    const geometry = new THREE.TorusGeometry(radius,thickness, 16, 64);
    const { color: baseColor, opacity } = getCSSColorWithOpacity(colorName);

    // 3D 입체감을 살리기 위해 조명의 영향을 받는 MeshStandardMaterial 사용
    const material = new THREE.MeshStandardMaterial({
        color: baseColor,
        emissive: baseColor,
        emissiveIntensity: 0.35,
        roughness: 0.25,
        metalness: 0.5,
        transparent: opacity < 1,
        opacity
    });

    return new THREE.Mesh(geometry, material);
}
// 5. 조명 생성 함수
function getLight(colorName) {
    const color = getCSSColorAsHex(colorName);
    const ambientLight = new THREE.AmbientLight(color, CONFIG.light.ambientIntensity);
    const pointLight = new THREE.PointLight(0xffffff, CONFIG.light.pointIntensity);
    pointLight.position.set(CONFIG.light.pointPos.x, CONFIG.light.pointPos.y, CONFIG.light.pointPos.z);
    
    return { ambientLight, pointLight };
}
// 6. 라인 관련 생성 함수들
function createBasicLine(points, options = {}) {
    const config = { colorName: "primary", linewidth: 2, transparent: false, opacity: 1, ...options };

    const geometry = new THREE.BufferGeometry().setFromPoints(points);
    const material = new THREE.LineBasicMaterial({
        color: getCSSColorAsHex(config.colorName),
        linewidth: config.linewidth,
        transparent: config.transparent,
        opacity: config.opacity
    });

    return new THREE.Line(geometry, material);
}
function createTubeLine(points, options = {}) {
    const config = { colorName: "primary", radius: 0.15, tubularSegments: 20, radialSegments: 8, emissiveIntensity: 0.3, ...options };

    const curve = new THREE.CatmullRomCurve3(points, true);
    const geometry = new THREE.TubeGeometry(curve, config.tubularSegments, config.radius, config.radialSegments, false);

    const material = new THREE.MeshStandardMaterial({
        color: getCSSColorAsHex(config.colorName),
        emissive: getCSSColorAsHex(config.colorName),
        emissiveIntensity: config.emissiveIntensity,
        roughness: 0.2,
        metalness: 0.6
    });

    return new THREE.Mesh(geometry, material);
}
function createStraightTubeLine(points, options = {}) {
    const config = { colorName: "primary", radius: 0.15, emissiveIntensity: 0.3, ...options };
    const group = new THREE.Group();

    for (let i = 0; i < points.length - 1; i++) {
        const start = points[i];
        const end = points[i + 1];
        const curve = new THREE.LineCurve3(start, end);
        const geometry = new THREE.TubeGeometry(curve, 8, config.radius, 8, false);

        const material = new THREE.MeshStandardMaterial({
            color: getCSSColorAsHex(config.colorName),
            emissive: getCSSColorAsHex(config.colorName),
            emissiveIntensity: config.emissiveIntensity,
            roughness: 0.2,
            metalness: 0.6
        });

        const mesh = new THREE.Mesh(geometry, material);
        group.add(mesh);
    }

    return group;
}

function createPentagonLine(starData, options = {}) {
    const config = { colorName: "primary", type: "basic", ...options };
    const points = starData.map(data => new THREE.Vector3(data.x, data.y, data.z));
    points.push(points[0]);

    if (config.type === "straightTube") {
        return createStraightTubeLine(points, config);
    } else if (config.type === "tube") {
        return createTubeLine(points, config);
    } else {
        return createBasicLine(points, config);
    }
}

// ============================================================================
// 메인 씬 초기화
// ============================================================================

function initThreeJSScene() {
    const container = document.getElementById('canvas-container') || document.body;
    const width = container.clientWidth;
    const height = container.clientHeight;
    const scene = new THREE.Scene();

    // 씬 기본 설정
    const bgColor = getCSSColorAsHex(CONFIG.scene.bgColor);
    const fogColor = getCSSColorAsHex(CONFIG.scene.fogColor);
    scene.background = new THREE.Color(bgColor);
    scene.fog = new THREE.FogExp2(fogColor, CONFIG.scene.fogDensity);

    // 카메라 설정
    const camera = new THREE.PerspectiveCamera(
        CONFIG.scene.fov,
        width / height,
        0.1,
        1000
    );
    camera.position.set(
        CONFIG.camera.initialPos.x,
        CONFIG.camera.initialPos.y,
        CONFIG.camera.initialPos.z
    );
    camera.lookAt(
        CONFIG.camera.target.x,
        CONFIG.camera.target.y,
        CONFIG.camera.target.z
    );

    // 렌더러 설정
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);

    // 광원 추가
    const { ambientLight, pointLight } = getLight("bmi");
    scene.add(ambientLight, pointLight);

    // 배경 원 구성
    const circleBig = createCircle(CONFIG.circle.big,  CONFIG.circle.thickness, CONFIG.circle.colorName);
    const circleMid = createCircle(CONFIG.circle.mid,  CONFIG.circle.thickness, CONFIG.circle.colorName);
    const circleSmall = createCircle(CONFIG.circle.small,  CONFIG.circle.thickness, CONFIG.circle.colorName);
    // 원 생성 이후 추가
    const circleGroup = new THREE.Group();
    circleGroup.add(circleBig, circleMid, circleSmall);
    circleGroup.position.z = 0.5;
    scene.add(circleGroup);

    // 별 및 차트 데이터 생성
    const { indivPoints, basePoints } = createPentagonStarData();
    const starObjects = [];
    const starGroup = new THREE.Group();

    indivPoints.forEach((point) => {
        const starMesh = new THREE.Mesh(
            new THREE.SphereGeometry(0.9, 18, 18),
            new THREE.MeshStandardMaterial({
                color: getCSSColorAsHex("bmi"),
                emissive: getCSSColorAsHex("bmi"),
                emissiveIntensity: 0.6,
                roughness: 0.3,
                metalness: 0.5
            })
        );

        starMesh.position.set(point.x, point.y, point.z);
        starMesh.userData = { ...point };
        starGroup.add(starMesh);
        starObjects.push(starMesh);
    });

    scene.add(starGroup);

    const basePentagonMesh = createPentagonFillMesh(basePoints, {
        color: "5각형3dmesh2",
        opacity: 0.4,
        emissiveIntensity: 0.4,
        zOffset: -0.5
    });
    const indivPentagonMesh = createPentagonFillMesh(indivPoints, {
        color: "5각형3dmesh1",
        opacity: 1,
        emissiveIntensity: 0.9,
        zOffset: 0
    });

    if (basePentagonMesh) scene.add(basePentagonMesh);
    if (indivPentagonMesh) scene.add(indivPentagonMesh);

    // 마우스 및 레이캐스터 인터랙션
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();
    const cameraTarget = new THREE.Vector3(
        CONFIG.camera.target.x,
        CONFIG.camera.target.y,
        CONFIG.camera.target.z
    );

    function updateCameraLookTarget() {
        camera.lookAt(cameraTarget.x, cameraTarget.y, cameraTarget.z);
    }

    window.addEventListener('click', (e) => {
        mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
        mouse.y = -(e.clientY / window.innerHeight) * 2 + 1;

        raycaster.setFromCamera(mouse, camera);
        const intersects = raycaster.intersectObjects(starObjects);

        if (intersects.length > 0) {
            const target = intersects[0].object;
            const data = target.userData;
            const focusPoint = new THREE.Vector3(data.x, data.y, data.z);

            gsap.to(camera.position, {
                x: data.x,
                y: data.y,
                z: data.z + CONFIG.camera.zoomDist,
                duration: 1.5,
                ease: "power3.inOut"
            });

            gsap.to(cameraTarget, {
                x: focusPoint.x,
                y: focusPoint.y,
                z: focusPoint.z,
                duration: 1.5,
                ease: "power3.inOut",
                onUpdate: updateCameraLookTarget,
                onComplete: updateCameraLookTarget
            });

            const hudPanel = document.getElementById('hud-panel');
            const starName = document.getElementById('star-name');
            const powerVal = document.getElementById('power-val');
            const resVal = document.getElementById('res-val');
            const powerBar = document.getElementById('power-bar');
            const resBar = document.getElementById('res-bar');

            if (starName) starName.innerText = data.name;
            if (hudPanel) hudPanel.classList.add('active');
            if (powerVal) powerVal.innerText = (data.indiv ?? 0) + "%";
            if (resVal) resVal.innerText = (data.M_base ?? 0) + "%";
            if (powerBar) powerBar.style.width = (data.indiv ?? 0) + "%";
            if (resBar) resBar.style.width = (data.M_base ?? 0) + "%";
        }
    });

    // 카메라 리셋
    window.resetCamera = function() {
        gsap.to(camera.position, {
            x: CONFIG.camera.initialPos.x,
            y: CONFIG.camera.initialPos.y,
            z: CONFIG.camera.initialPos.z,
            duration: 1.5,
            ease: "power3.inOut"
        });

        gsap.to(cameraTarget, {
            x: CONFIG.camera.target.x,
            y: CONFIG.camera.target.y,
            z: CONFIG.camera.target.z,
            duration: 1.5,
            ease: "power3.inOut",
            onUpdate: updateCameraLookTarget,
            onComplete: updateCameraLookTarget
        });

        document.getElementById('hud-panel').classList.remove('active');
        document.getElementById('power-bar').style.width = "0%";
        document.getElementById('res-bar').style.width = "0%";
    };

    // 애니메이션 루프
    function animate() {
        requestAnimationFrame(animate);
        renderer.render(scene, camera);
    }
    animate();

    // 창 크기 변경 대응
    window.addEventListener('resize', () => {
        const newWidth = container.clientWidth;
        const newHeight = container.clientHeight;

        camera.aspect = newWidth / newHeight;
        camera.updateProjectionMatrix(); // 변경된 비율을 반영하는 필수 메서드

        renderer.setSize(newWidth, newHeight);
    });
}

document.addEventListener('DOMContentLoaded', initThreeJSScene);