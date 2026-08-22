import React, { useRef, useEffect, useState } from 'react';
import * as THREE from 'three';
import './ThreeDVisualization.css';

const ThreeDVisualization = ({ traces = [] }) => {
  const mountRef = useRef(null);
  const sceneRef = useRef(null);
  const cameraRef = useRef(null);
  const rendererRef = useRef(null);
  const particlesRef = useRef([]);
  const animationIdRef = useRef(null);
  const [isRotating, setIsRotating] = useState(true);

  useEffect(() => {
    if (!mountRef.current) return;

    // Scene setup
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0a0e1a);
    scene.fog = new THREE.Fog(0x0a0e1a, 50, 200);

    // Camera
    const camera = new THREE.PerspectiveCamera(
      75,
      mountRef.current.clientWidth / mountRef.current.clientHeight,
      0.1,
      1000
    );
    camera.position.z = 50;
    camera.position.y = 20;

    // Renderer
    const renderer = new THREE.WebGLRenderer({ 
      antialias: true,
      alpha: true 
    });
    renderer.setSize(mountRef.current.clientWidth, mountRef.current.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    mountRef.current.appendChild(renderer.domElement);

    sceneRef.current = scene;
    cameraRef.current = camera;
    rendererRef.current = renderer;

    // Create particles representing traces
    const createParticles = () => {
      // Clear existing particles
      particlesRef.current.forEach(particle => {
        scene.remove(particle);
      });
      particlesRef.current = [];

      // Create new particles from traces
      const particleCount = Math.min(traces.length, 100);
      
      for (let i = 0; i < particleCount; i++) {
        const trace = traces[i] || { is_anomalous: false, combined_score: 0 };
        
        // Particle geometry
        const geometry = new THREE.SphereGeometry(
          trace.is_anomalous ? 0.8 : 0.5, 
          16, 
          16
        );
        
        // Color based on anomaly status
        const material = new THREE.MeshPhongMaterial({
          color: trace.is_anomalous ? 0xff4444 : 0x4444ff,
          emissive: trace.is_anomalous ? 0xff0000 : 0x0000ff,
          emissiveIntensity: trace.combined_score * 2,
          transparent: true,
          opacity: 0.8,
        });

        const particle = new THREE.Mesh(geometry, material);

        // Position in 3D space
        const angle = (i / particleCount) * Math.PI * 2;
        const radius = 30 + Math.random() * 20;
        const height = (Math.random() - 0.5) * 30;

        particle.position.x = Math.cos(angle) * radius;
        particle.position.y = height;
        particle.position.z = Math.sin(angle) * radius;

        // Animation properties
        particle.userData = {
          velocity: new THREE.Vector3(
            (Math.random() - 0.5) * 0.1,
            (Math.random() - 0.5) * 0.1,
            (Math.random() - 0.5) * 0.1
          ),
          originalY: height,
          time: Math.random() * Math.PI * 2,
          isAnomalous: trace.is_anomalous
        };

        scene.add(particle);
        particlesRef.current.push(particle);
      }

      // Add connecting lines between nearby particles
      const lineGeometry = new THREE.BufferGeometry();
      const lineMaterial = new THREE.LineBasicMaterial({
        color: 0x444466,
        transparent: true,
        opacity: 0.3
      });

      const positions = [];
      for (let i = 0; i < particlesRef.current.length; i++) {
        for (let j = i + 1; j < particlesRef.current.length; j++) {
          const p1 = particlesRef.current[i].position;
          const p2 = particlesRef.current[j].position;
          
          const distance = p1.distanceTo(p2);
          if (distance < 15) {
            positions.push(p1.x, p1.y, p1.z);
            positions.push(p2.x, p2.y, p2.z);
          }
        }
      }

      lineGeometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
      const lines = new THREE.LineSegments(lineGeometry, lineMaterial);
      scene.add(lines);
      particlesRef.current.push(lines);
    };

    createParticles();

    // Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
    scene.add(ambientLight);

    const pointLight1 = new THREE.PointLight(0x6366f1, 1, 100);
    pointLight1.position.set(20, 20, 20);
    scene.add(pointLight1);

    const pointLight2 = new THREE.PointLight(0xff4444, 1, 100);
    pointLight2.position.set(-20, -20, -20);
    scene.add(pointLight2);

    // Add grid helper
    const gridHelper = new THREE.GridHelper(100, 20, 0x444466, 0x222233);
    gridHelper.position.y = -20;
    scene.add(gridHelper);

    // Animation
    let time = 0;
    const animate = () => {
      animationIdRef.current = requestAnimationFrame(animate);
      time += 0.01;

      // Rotate camera
      if (isRotating) {
        camera.position.x = Math.cos(time * 0.2) * 50;
        camera.position.z = Math.sin(time * 0.2) * 50;
        camera.lookAt(0, 0, 0);
      }

      // Animate particles
      particlesRef.current.forEach((particle, index) => {
        if (particle.userData && particle.userData.velocity) {
          // Floating animation
          particle.userData.time += 0.02;
          particle.position.y = particle.userData.originalY + Math.sin(particle.userData.time) * 3;

          // Pulsing for anomalies
          if (particle.userData.isAnomalous) {
            const scale = 1 + Math.sin(time * 5 + index) * 0.2;
            particle.scale.set(scale, scale, scale);
          }

          // Rotation
          particle.rotation.y += 0.01;
        }
      });

      renderer.render(scene, camera);
    };

    animate();

    // Handle resize
    const handleResize = () => {
      if (!mountRef.current) return;
      
      camera.aspect = mountRef.current.clientWidth / mountRef.current.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(mountRef.current.clientWidth, mountRef.current.clientHeight);
    };

    window.addEventListener('resize', handleResize);

    // Cleanup
    return () => {
      window.removeEventListener('resize', handleResize);
      if (animationIdRef.current) {
        cancelAnimationFrame(animationIdRef.current);
      }
      if (mountRef.current && renderer.domElement) {
        mountRef.current.removeChild(renderer.domElement);
      }
      renderer.dispose();
    };
  }, [traces, isRotating]);

  return (
    <div className="three-d-container">
      <div className="three-d-header">
        <h3 className="three-d-title">
          <span className="three-d-icon">🌐</span>
          3D Trace Visualization
        </h3>
        <div className="three-d-controls">
          <button 
            className={`control-btn ${isRotating ? 'active' : ''}`}
            onClick={() => setIsRotating(!isRotating)}
          >
            {isRotating ? '⏸ Pause' : '▶ Rotate'}
          </button>
        </div>
      </div>
      <div className="three-d-legend">
        <div className="legend-item">
          <div className="legend-dot normal"></div>
          <span>Normal Traces</span>
        </div>
        <div className="legend-item">
          <div className="legend-dot anomalous"></div>
          <span>Anomalous Traces</span>
        </div>
      </div>
      <div ref={mountRef} className="three-d-mount" />
      <div className="three-d-info">
        <p>Interactive 3D visualization of agent execution traces</p>
        <p className="info-detail">Anomalies pulsate • Lines show trace relationships • Auto-rotating view</p>
      </div>
    </div>
  );
};

export default ThreeDVisualization;
