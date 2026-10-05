
# OPERON

**A Human-Supervised AI Operating System for Small Service Businesses**

Concordia University | SOEN 490 Capstone Project | 2026–2027

**Project Sponsor:** FA Systems Technologies Inc.

Operon is an AI-powered internal web application designed to help small service businesses streamline their operations through shared business knowledge, specialized AI agents, and human supervision.

Developed in collaboration with FA Systems Technologies Inc., the project aims to reduce repetitive administrative work, improve coordination, and maintain consistency throughout client onboarding, launch preparation, communication, and performance review.

Rather than operating autonomously, Operon generates evidence-backed drafts and recommendations that authorized users can review, edit, and approve. Its central principle is to combine AI-assisted productivity with human accountability.

---

# Release Demos

The project is developed over three major releases during the 2026–2027 academic year.

| Release | Date | Demo |
|---|---|---|
| Release 1 | November 10, 2026 | Coming soon |
| Release 2 | January 29, 2027 | Coming soon |
| Final Release | April 13, 2027 | Coming soon |

Demo recordings, deployment links, and release notes will be added as each release is completed.

---

# Project Summary

## The Problem

Small service businesses often manage their operations across disconnected tools, documents, conversations, and individual employees' knowledge.

For FA Systems, onboarding a new client involves gathering information, understanding business requirements, preparing marketing and operational materials, and coordinating communications.

As the number of clients increases, these activities introduce repetitive work, fragmented information, inconsistent processes, and additional coordination overhead.

Operon aims to address these challenges by providing a unified workspace where business knowledge is maintained and AI-assisted workflows support employees throughout the client delivery process.

## Our Solution

Operon is organized around three interconnected components.

### 1. The Brain — Shared Business Context

The Brain serves as the central knowledge foundation of Operon.

It maintains business playbooks, client information, operational requirements, approved decisions, and supporting source documents.

By maintaining versioned and approved information, it allows different AI workflows to access consistent business context without repeatedly collecting the same information.

Key responsibilities include:

- Maintaining structured client profiles and business knowledge.
- Managing source documents and approved playbooks.
- Tracking information provenance and version history.
- Providing authorized, client-specific context to AI workflows.

### 2. The Workforce — Specialized AI Agents

The Workforce consists of specialized, task-oriented AI agents that use the Brain to assist with business operations.

Each agent performs a defined workflow and produces structured drafts or recommendations for human review.

The project initially focuses on client onboarding, with additional workflows planned for later releases.

| Agent | Responsibility | Planned Release |
|---|---|---|
| Onboarding Agent | Extracts client requirements, prepares client profiles, and identifies missing or conflicting information. | Release 1 |
| Launch Preparation Agent | Prepares campaign briefs and qualification instructions using approved client information. | Release 2 |
| Communication Agent | Drafts client updates, information requests, and approval requests. | Release 2 |
| Early Performance Agent | Analyzes available operational data and identifies issues requiring human investigation. | Final Release (conditional) |

The agents share the same approved business context and follow a common review and approval process.

Their outputs remain drafts until explicitly approved by an authorized user.

### 3. The Command Center — Human Supervision

The Command Center provides a centralized interface for employees to oversee clients, AI-generated outputs, and business workflows.

Its planned capabilities include:

- Client workspaces and delivery status.
- AI-generated draft review and editing.
- Human approval and rejection.
- Role-based access control.
- Version history and audit logs.
- Visibility into workflow execution and failures.

The Command Center is designed to keep employees informed and in control while reducing repetitive operational work.

## Core Design Principles

**Shared Context:** AI workflows use consistent, versioned business knowledge rather than isolated conversations.

**Human Supervision:** AI-generated outputs require explicit review and approval before being used.

**Traceability:** Generated artifacts are linked to their source information, context versions, and approval history.

**Privacy and Security:** Client information is isolated through authorization controls, and sensitive data is minimized when interacting with AI providers.

**Provider Independence:** The AI integration layer is designed to support different model providers without tightly coupling the application to a single vendor.

**Measurable Value:** The team will evaluate output accuracy, preparation time, correction effort, and operational usefulness instead of relying solely on the number of implemented agents.

## Development Roadmap

| Release | Main Objectives |
|---|---|
| Release 1 | Establish the platform foundation, shared context store, onboarding agent, access controls, human approval, and audit history. |
| Release 2 | Extend the platform with launch preparation and client communication workflows using approved business context. |
| Final Release | Improve reliability, evaluate operational usefulness, complete deployment and handover, and introduce early performance analysis if reliable data is available. |

The first release prioritizes one complete, evaluated onboarding workflow before expanding the system.

Later features are subject to technical feasibility, evaluation results, and team capacity.

---

# Developer Getting Started Guide

This section provides the starting point for developers joining the Operon project.

The development environment and commands will be finalized once the team confirms its technology stack and integrates the initial application.

## Prerequisites

The proposed development stack includes:

| Component | Proposed Technology |
|---|---|
| Frontend | React, TypeScript, Vite |
| Backend | C# / ASP.NET Core (.NET 10) |
| Database | PostgreSQL |
| Data Access | Entity Framework Core |
| Authentication | ASP.NET Core Identity |
| Containerization | Docker Compose |
| Continuous Integration | GitHub Actions |

These technologies are the proposed architecture from the project plan and should be updated to reflect the team's final implementation.

## 1. Clone the Repository

Clone the project using Git:

```bash
git clone https://github.com/2Nony3/SOEN-490.git
cd SOEN-490
```

## 2. Configure the Development Environment

Follow the environment configuration instructions provided by the team.

Once the application skeleton is integrated, this section will document the required dependencies, environment variables, database configuration, and local services.

Use synthetic or approved anonymized client data during development.

Never commit API keys, passwords, environment secrets, or confidential client information to the repository.

## 3. Run the Application

The verified commands for installing dependencies, starting the frontend and backend, and initializing the database will be added once the team's development environment is finalized.

## 4. Run the Tests

The team will maintain automated tests for the application's core business logic, APIs, access controls, and AI workflows.

Exact testing commands will be documented alongside the implementation.

## 5. Contributing

All development work is coordinated through GitHub Issues, Projects, and Pull Requests.

Contributors should:

1. Select an assigned issue and review its acceptance criteria.
2. Create a dedicated branch for the task.
3. Implement the feature and its associated tests.
4. Open a pull request linked to the relevant issue.
5. Obtain code review and ensure the required checks pass before merging.

Changes affecting authentication, client data isolation, or other security-sensitive functionality require particular attention during review.

Follow the course requirements for acknowledging AI-assisted contributions.

**Project Board:** [GitHub Projects — Link to be added]

**CI Status:** To be added after the workflow is configured.

---


# Wiki Table of Contents

The [Operon GitHub Wiki](https://github.com/2Nony3/SOEN-490/wiki) contains the project's technical documentation, planning records, and course deliverables.

| # | Documentation |
|---|---|
| 01 | Meeting Minutes |
| 02 | Risks |
| 03 | User Consent and End-User License Agreement |
| 04 | Legal and Ethical Issues |
| 05 | Economic |
| 06 | Budget |
| 07 | Personas |
| 08 | Mockups |
| 09 | Diversity Statement |
| 10 | Overall Architecture and Class Diagrams |
| 11 | Infrastructure and Tools |
| 12 | Naming Conventions |
| 13 | Testing Plan and Continuous Integration |
| 14 | Security |
| 15 | Performance |
| 16 | Deployment Plan and Infrastructure |
| 17 | Missing Knowledge and Independent Learning |

Visit the [GitHub Wiki](https://github.com/2Nony3/SOEN-490/wiki) to access the individual pages.

---

# Equity and Diversity

The Operon team is committed to developing software that respects diversity, promotes accessibility, and supports inclusive collaboration.

As an AI-assisted business application, Operon must account for the possibility of inaccurate or biased AI-generated recommendations. Human review, transparent source information, and controlled access are essential to ensuring that automated outputs remain accountable.

The team aims to design an interface accessible to users with varying levels of technical expertise and to evaluate the system using diverse and representative business scenarios.

All team members are encouraged to contribute meaningfully throughout the software development process, regardless of their experience or technical specialization.
