# 🏗️ Software Architecture & Design Guidelines

## 📐 SOLID Principles in Practice

### **S - Single Responsibility Principle**
*"A class should have one, and only one, reason to change"*

#### ✅ CORRECT - Single Responsibility Per Class
- **Validators**: Responsible ONLY for validation logic.
- **Repositories**: Responsible ONLY for database operations.
- **Services**: Orchestrate the workflow between validators, repositories, and external providers.

### **O - Open/Closed Principle**
*"Software entities should be open for extension, closed for modification"*

#### ✅ CORRECT - Extension Without Modification
Use abstract base classes (Interfaces) for external providers (e.g., `StockPriceProvider`). Adding a new provider (IEX, Bloomberg) should only require adding a new class, not changing the service logic.

### **L - Liskov Substitution Principle**
*"Objects should be replaceable with instances of their subtypes without altering correctness"*

### **I - Interface Segregation Principle**
*"Clients should not be forced to depend on interfaces they don't use"*

### **D - Dependency Inversion Principle**
*"Depend on abstractions, not concretions"*

---

## 🎨 Essential Design Patterns

### **1. Repository Pattern**
Abstracts data access logic. Business logic should never call the database driver directly.

### **2. Factory Pattern**
Creates objects (like Notification providers) without specifying the exact class.

### **3. Strategy Pattern**
Defines a family of algorithms (like Portfolio Pricing strategies) and makes them interchangeable at runtime.

---

## 🏛️ Project Structure

### **Backend Layered Architecture**
1. **API Layer**: Route handlers, DTOs, and Middleware.
2. **Application Layer**: Use cases and orchestration.
3. **Domain Layer**: Core business entities and abstract interfaces.
4. **Infrastructure Layer**: Concrete implementations of repositories and external providers.

### **Frontend Feature-Based Architecture**
Organize by feature (e.g., `features/watchlists`, `features/stocks`) rather than technical type where possible.

---

## 🧪 Testing Architecture
- **Unit Tests**: Isolated, no DB/Network.
- **Integration Tests**: Multiple components (e.g., API + DB).
- **E2E Tests**: Complete user flows using Playwright.

---

## 📊 Error Handling
- Use custom application exceptions (`AppException`).
- Centralized error mapping in middleware.
- Never return raw internal error messages to the client in production.
