import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-app.js";
import { getFirestore } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-firestore.js";

const firebaseConfig = {
  apiKey: "AIzaSyB7mjGnIXbsEsbc6UR7avoBxz8Z6Tycpuk",
  authDomain: "security-system-52ae0.firebaseapp.com",
  projectId: "security-system-52ae0",
  storageBucket: "security-system-52ae0.firebasestorage.app",
  messagingSenderId: "1018405172015",
  appId: "1:1018405172015:web:e2f966aba70e6ec93ce7da",
  measurementId: "G-TCKP0KXC20"
};

const app = initializeApp(firebaseConfig);
export const db = getFirestore(app);
