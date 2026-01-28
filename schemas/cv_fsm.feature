Feature: CV Generator FSM

  Scenario: Any edit forces REVIEW
    Given current_state is EXECUTE
    And user_message contains "zmień doświadczenie"
    When resolve_stage is called
    Then next_state should be REVIEW

  Scenario: Cannot execute without readiness
    Given current_state is CONFIRM
    And validation_passed is false
    When generate_requested
    Then next_state should be REVIEW

  Scenario: Happy path to PDF
    Given current_state is CONFIRM
    And validation_passed is true
    And readiness_ok is true
    When generate_requested
    Then next_state should be EXECUTE
    And on pdf_generated next_state should be DONE

  Scenario: PDF failure returns to REVIEW
    Given current_state is EXECUTE
    When pdf_failed
    Then next_state should be REVIEW

  Scenario: Edit after DONE returns to REVIEW
    Given current_state is DONE
    And user_message contains "dodaj certyfikat"
    When resolve_stage is called
    Then next_state should be REVIEW

  Scenario: Confirmation gate blocks execute
    Given current_state is REVIEW
    And confirmation_required is true
    When generate_requested
    Then next_state should not be EXECUTE

  Scenario: Validation failure loops safely
    Given current_state is CONFIRM
    When validation_failed
    Then next_state should be REVIEW

