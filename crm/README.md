# CRM Application - Celery Setup Guide

This document provides instructions on how to set up and run the Celery components for handling asynchronous and scheduled tasks, such as generating the weekly CRM report.

## 1. Prerequisites

- **Install Redis:** Celery uses Redis as a message broker. If you don't have it, install it via Homebrew:
  ```bash
  brew install redis