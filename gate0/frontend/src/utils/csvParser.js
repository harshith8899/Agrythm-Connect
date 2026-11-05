import Papa from 'papaparse';

/**
 * Utility function to parse CSV files or strings safely using papaparse
 * @param {string|File} input - CSV raw string or File object
 * @param {object} options - Optional PapaParse configuration options
 * @returns {Promise<object>} - Parsed data with rows and errors
 */
export const parseCSV = (input, options = {}) => {
  return new Promise((resolve, reject) => {
    Papa.parse(input, {
      header: true,
      skipEmptyLines: true,
      dynamicTyping: true,
      complete: (results) => resolve(results),
      error: (error) => reject(error),
      ...options,
    });
  });
};
