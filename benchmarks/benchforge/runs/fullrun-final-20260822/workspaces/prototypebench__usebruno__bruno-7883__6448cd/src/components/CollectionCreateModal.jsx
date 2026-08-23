import React from 'react';
import { useFormik } from 'formik';
import { validateName } from '../utils/validation';

const CollectionCreateModal = ({ isOpen, onClose, onCreate }) => {
  if (!isOpen) return null;

  const formik = useFormik({
    initialValues: {
      name: ''
    },
    validate: (values) => {
      const errors = {};
      const nameError = validateName(values.name, 'Collection name');
      if (nameError) {
        errors.name = nameError;
      }
      return errors;
    },
    onSubmit: (values) => {
      onCreate(values.name.trim());
      onClose();
    }
  });

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <h2>Create Collection</h2>
        <form onSubmit={formik.handleSubmit}>
          <div className="form-group">
            <label htmlFor="name">Collection Name</label>
            <input
              id="name"
              name="name"
              type="text"
              value={formik.values.name}
              onChange={(e) => {
                // Fix stale Formik values by ensuring we update with current value
                formik.setFieldValue('name', e.target.value);
                // Also update touched state
                formik.setFieldTouched('name', true, false);
              }}
              onBlur={formik.handleBlur}
              className={formik.touched.name && formik.errors.name ? 'error' : ''}
            />
            {formik.touched.name && formik.errors.name && (
              <div className="error-message">{formik.errors.name}</div>
            )}
          </div>
          <div className="modal-actions">
            <button type="button" onClick={onClose} className="btn-secondary">
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={formik.isSubmitting}>
              Create
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default CollectionCreateModal;