import { useState } from "react";
import { Link } from "react-router-dom";

interface WelcomeWizardProps {
  onComplete: () => void;
}

type Step = 1 | 2 | 3;

export default function WelcomeWizard({ onComplete }: WelcomeWizardProps) {
  const [step, setStep] = useState<Step>(1);
  const [completedSteps, setCompletedSteps] = useState<Set<Step>>(new Set());

  function markStepComplete(s: Step) {
    setCompletedSteps((prev) => new Set([...prev, s]));
  }

  function handleNext() {
    if (step < 3) {
      markStepComplete(step);
      setStep((step + 1) as Step);
    }
  }

  function handlePrev() {
    if (step > 1) {
      setStep((step - 1) as Step);
    }
  }

  function handleFinish() {
    markStepComplete(3);
    onComplete();
  }

  return (
    <div className="wizard-overlay">
      <div className="wizard-container">
        {/* Progress indicator */}
        <div className="wizard-progress">
          <div className={`progress-step ${step >= 1 ? "active" : ""} ${completedSteps.has(1) ? "completed" : ""}`}>
            <div className="progress-num">1</div>
            <div className="progress-label">GitHub</div>
          </div>
          <div className={`progress-line ${step > 1 ? "active" : ""}`} />
          <div className={`progress-step ${step >= 2 ? "active" : ""} ${completedSteps.has(2) ? "completed" : ""}`}>
            <div className="progress-num">2</div>
            <div className="progress-label">Stripe</div>
          </div>
          <div className={`progress-line ${step > 2 ? "active" : ""}`} />
          <div className={`progress-step ${step >= 3 ? "active" : ""} ${completedSteps.has(3) ? "completed" : ""}`}>
            <div className="progress-num">3</div>
            <div className="progress-label">Project</div>
          </div>
        </div>

        {/* Step 1: GitHub Setup */}
        {step === 1 && (
          <div className="wizard-step">
            <div className="wizard-header">
              <h1>Connect Your GitHub Repository</h1>
              <p>Link your GitHub repo so we can generate Stripe integration code and push it directly to your codebase.</p>
            </div>

            <div className="wizard-content">
              <div className="wizard-section">
                <h3>Why connect GitHub?</h3>
                <ul className="wizard-benefits">
                  <li>✓ Auto-generate TypeScript/Python Stripe client code</li>
                  <li>✓ Push generated code directly to your repository</li>
                  <li>✓ Create pull requests for review</li>
                  <li>✓ Track webhook handlers and payment flows</li>
                </ul>
              </div>

              <div className="wizard-action">
                <p className="wizard-hint">Next step: Connect your GitHub account in the Agency section</p>
                <Link to="/agency" className="button button-primary">
                  Go to Agency Settings →
                </Link>
              </div>

              <div className="wizard-tip">
                <strong>💡 Tip:</strong> You need to be an org owner or have admin access to the repository.
              </div>
            </div>

            <div className="wizard-footer">
              <button onClick={handleNext} className="button button-primary">
                Next Step
              </button>
            </div>
          </div>
        )}

        {/* Step 2: Stripe Configuration */}
        {step === 2 && (
          <div className="wizard-step">
            <div className="wizard-header">
              <h1>Add Your Stripe API Keys</h1>
              <p>Store your Stripe API credentials securely in the vault. These are used to generate and test your integration.</p>
            </div>

            <div className="wizard-content">
              <div className="wizard-section">
                <h3>What you'll need</h3>
                <ul className="wizard-benefits">
                  <li>✓ Stripe Secret Key (starts with sk_)</li>
                  <li>✓ Stripe Publishable Key (starts with pk_)</li>
                  <li>✓ (Optional) Webhook signing secret</li>
                </ul>
              </div>

              <div className="wizard-steps-list">
                <div className="wizard-step-item">
                  <span className="step-num">1</span>
                  <div>
                    <strong>Log in to Stripe Dashboard</strong>
                    <p>Go to <a href="https://dashboard.stripe.com/apikeys" target="_blank" rel="noopener noreferrer">Developers → API Keys</a></p>
                  </div>
                </div>
                <div className="wizard-step-item">
                  <span className="step-num">2</span>
                  <div>
                    <strong>Copy your keys</strong>
                    <p>You'll find both Secret and Publishable keys on this page</p>
                  </div>
                </div>
                <div className="wizard-step-item">
                  <span className="step-num">3</span>
                  <div>
                    <strong>Store in Project Vault</strong>
                    <p>After creating your first project, go to Project Settings → Vault to securely store them</p>
                  </div>
                </div>
              </div>

              <div className="wizard-tip">
                <strong>🔒 Security:</strong> Your API keys are encrypted and never exposed in logs or the frontend.
              </div>
            </div>

            <div className="wizard-footer">
              <button onClick={handlePrev} className="button button-secondary">
                Back
              </button>
              <button onClick={handleNext} className="button button-primary">
                Next Step
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Create First Project */}
        {step === 3 && (
          <div className="wizard-step">
            <div className="wizard-header">
              <h1>You're Ready! Create Your First Project</h1>
              <p>A project represents one Stripe integration. You can manage multiple projects independently.</p>
            </div>

            <div className="wizard-content">
              <div className="wizard-section">
                <h3>What happens when you create a project?</h3>
                <ul className="wizard-benefits">
                  <li>✓ Dashboard shows readiness score and diagnostics</li>
                  <li>✓ Run health checks and webhook validation</li>
                  <li>✓ Generate SDK code (Node.js, Python)</li>
                  <li>✓ Predictive analysis and auto-healing</li>
                  <li>✓ Full audit logs and monitoring</li>
                </ul>
              </div>

              <div className="wizard-section">
                <h3>Value Dashboard</h3>
                <div className="wizard-value-box">
                  <div className="value-item">
                    <div className="value-icon">📊</div>
                    <div>
                      <strong>Readiness Score</strong>
                      <p>See at a glance if your integration is production-ready</p>
                    </div>
                  </div>
                  <div className="value-item">
                    <div className="value-icon">🤖</div>
                    <div>
                      <strong>Autonomous Automation</strong>
                      <p>The system detects issues and recommends (or auto-fixes) them</p>
                    </div>
                  </div>
                  <div className="value-item">
                    <div className="value-icon">🔍</div>
                    <div>
                      <strong>Code Generation</strong>
                      <p>Generate production-ready webhook handlers and client SDKs</p>
                    </div>
                  </div>
                  <div className="value-item">
                    <div className="value-icon">🚀</div>
                    <div>
                      <strong>Deploy Pipeline</strong>
                      <p>Automated testing, code review integration, and deployment</p>
                    </div>
                  </div>
                </div>
              </div>

              <div className="wizard-tip">
                <strong>⏱️ Quick Start:</strong> You'll see your first dashboard in ~60 seconds after creating a project.
              </div>
            </div>

            <div className="wizard-footer">
              <button onClick={handlePrev} className="button button-secondary">
                Back
              </button>
              <button onClick={handleFinish} className="button button-success">
                Get Started →
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
